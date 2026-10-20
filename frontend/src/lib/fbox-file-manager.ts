/**
 * FBA 本地工程文件 (.fbox) — 读取、保存、版本迁移、File System Access API。
 */
import { DEFAULT_THROW_RATIO } from "@/constants";
import {
  buildTaskHistorySnapshot,
  newTaskId,
  type TaskHistorySnapshot,
  type WorkflowSnapshotSource,
} from "@/lib/task-history-snapshot";
import { EMPTY_ROW } from "@/lib/step1-rows";
import { autoTaskName } from "@/lib/workflow-storage";
import { createEmptyStaleness } from "@/lib/workflow-invalidation";
import { DEFAULT_TRANSPORT_MODE } from "@/lib/transport-mode";

/** 当前软件支持的 .fbox 格式版本（递增时请在 migrateProjectData 中补迁移链）。 */
export const FBOX_CURRENT_VERSION = 1;

const FBOX_EXTENSION = ".fbox";
const FBOX_MIME = "application/json";

export interface FboxSettings {
  step?: number;
  throw_ratio?: number;
}

export interface FboxProjectFile {
  version: number;
  task_id: string;
  task_name: string;
  saved_at: string;
  /** 完整工作流快照（与后端任务历史结构一致，便于向下兼容）。 */
  grid_data: TaskHistorySnapshot;
  settings: FboxSettings;
}

export type FboxSaveStatus = "idle" | "saving" | "saved" | "error";

export function isFileSystemAccessSupported(): boolean {
  return typeof window !== "undefined" && "showSaveFilePicker" in window;
}

export function defaultFboxFileName(taskName?: string): string {
  const base = (taskName || autoTaskName()).replace(/[<>:"/\\|?*]/g, "_");
  return base.toLowerCase().endsWith(FBOX_EXTENSION) ? base : `${base}${FBOX_EXTENSION}`;
}

function emptyWorkflowSource(taskId: string, taskName: string): WorkflowSnapshotSource {
  return {
    taskId,
    taskName,
    step: 1,
    inputRows: [{ ...EMPTY_ROW }],
    fnskuOverrides: {},
    boxEditorApi: [],
    boxLocked: false,
    throwRatio: DEFAULT_THROW_RATIO,
    step3Matrix: [],
    step3BoxCount: 0,
    step3SkuCount: 0,
    metrics: [],
    tailPool: [],
    hasOverweight: false,
    step4Ok: false,
    step4StatusLines: [],
    step4Errors: [],
    workerPackingPreview: [],
    workerPackingWarehouses: [],
    forwarder: [],
    shippingSheet: [],
    shippingSheetLegend: [],
    shipments: [],
    actualPlacementFee: null,
    selectedShipmentId: "",
    invoiceDraft: null,
    invoiceTemplateBase64: null,
    invoiceSessionsByShipment: {},
    invoiceForwarderId: "",
    invoicePoByShipment: {},
    invoiceSyncLinkedEdits: true,
    customsSession: null,
    highestReachedStep: 1,
    staleness: createEmptyStaleness(),
    transportMode: DEFAULT_TRANSPORT_MODE,
  };
}

export function buildFboxFromSource(source: WorkflowSnapshotSource): FboxProjectFile {
  return {
    version: FBOX_CURRENT_VERSION,
    task_id: source.taskId,
    task_name: source.taskName,
    saved_at: new Date().toISOString(),
    grid_data: buildTaskHistorySnapshot(source),
    settings: {
      step: source.step,
      throw_ratio: source.throwRatio,
    },
  };
}

export function createEmptyFbox(taskId: string, taskName: string): FboxProjectFile {
  return buildFboxFromSource(emptyWorkflowSource(taskId, taskName));
}

function normalizeV1(raw: Record<string, unknown>): FboxProjectFile {
  const grid =
    (raw.grid_data as TaskHistorySnapshot | undefined) ??
    (raw as unknown as TaskHistorySnapshot);

  const taskId = String(raw.task_id ?? grid.task_id ?? newTaskId());
  const taskName = String(raw.task_name ?? grid.task_name ?? autoTaskName());

  const settings: FboxSettings = {
    ...(typeof raw.settings === "object" && raw.settings !== null
      ? (raw.settings as FboxSettings)
      : {}),
  };
  if (settings.step == null && grid.step != null) settings.step = Number(grid.step);
  if (settings.throw_ratio == null && grid.react_throw_ratio != null) {
    settings.throw_ratio = Number(grid.react_throw_ratio);
  }

  return {
    version: FBOX_CURRENT_VERSION,
    task_id: taskId,
    task_name: taskName,
    saved_at: String(raw.saved_at ?? grid.saved_at ?? new Date().toISOString()),
    grid_data: {
      ...grid,
      task_id: taskId,
      task_name: taskName,
      step: Number(settings.step ?? grid.step ?? 1),
    },
    settings,
  };
}

/**
 * 将磁盘 JSON 迁移到当前版本。旧版/缺字段时补全，不抛错（无法识别时抛错）。
 */
export function migrateProjectData(parsed: unknown): FboxProjectFile {
  if (parsed == null || typeof parsed !== "object") {
    throw new Error("工程文件格式无效：根节点必须是 JSON 对象");
  }

  const raw = parsed as Record<string, unknown>;
  let version = Number(raw.version ?? 0);

  // 无 version 但含任务字段 → 视为 v0 裸快照，升级到 v1
  if (!version && (raw.task_id != null || raw.input_df != null || raw.grid_data != null)) {
    version = 1;
  }

  if (version < 1) {
    throw new Error("无法识别的工程文件版本");
  }

  if (version === 1) {
    return normalizeV1(raw);
  }

  // 未来 version 2：在此链式迁移
  // if (version === 2) return migrateV2toCurrent(raw);

  if (version > FBOX_CURRENT_VERSION) {
    throw new Error(
      `工程文件版本 (v${version}) 高于当前软件 (v${FBOX_CURRENT_VERSION})，请升级软件后打开`,
    );
  }

  throw new Error(`不支持的工程文件版本: ${version}`);
}

export function serializeFboxProject(project: FboxProjectFile): string {
  return JSON.stringify(project, null, 2);
}

export async function writeFboxToHandle(
  handle: FileSystemFileHandle,
  project: FboxProjectFile,
): Promise<void> {
  const writable = await handle.createWritable();
  await writable.write(serializeFboxProject(project));
  await writable.close();
}

export async function readFboxFromHandle(handle: FileSystemFileHandle): Promise<FboxProjectFile> {
  const file = await handle.getFile();
  return parseFboxText(await file.text());
}

export function parseFboxText(text: string): FboxProjectFile {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("工程文件不是有效的 JSON");
  }
  return migrateProjectData(parsed);
}

export async function pickSaveNewFbox(
  suggestedName: string,
): Promise<{ handle: FileSystemFileHandle; name: string }> {
  if (!isFileSystemAccessSupported()) {
    throw new Error("当前环境不支持本地文件保存，请使用 Chrome / Edge 桌面浏览器");
  }
  const handle = await window.showSaveFilePicker({
    suggestedName: defaultFboxFileName(suggestedName),
    types: [
      {
        description: "FBA 工程文件",
        accept: { [FBOX_MIME]: [FBOX_EXTENSION] },
      },
    ],
  });
  return { handle, name: handle.name };
}

export function isFboxFileName(name: string): boolean {
  return name.toLowerCase().endsWith(FBOX_EXTENSION);
}

export function isFboxFileDrag(event: DragEvent): boolean {
  const dt = event.dataTransfer;
  if (!dt) return false;
  if (dt.types.includes("Files")) {
    const items = dt.items;
    if (items?.length) {
      for (let i = 0; i < items.length; i += 1) {
        const item = items[i];
        if (item.kind !== "file") continue;
        const file = item.getAsFile();
        if (file && isFboxFileName(file.name)) return true;
      }
    }
  }
  return false;
}

type DataTransferItemWithHandle = DataTransferItem & {
  getAsFileSystemHandle?: () => Promise<FileSystemHandle>;
};

export async function resolveFboxFromDataTransfer(
  dt: DataTransfer,
): Promise<{ handle: FileSystemFileHandle | null; file: File } | null> {
  const items = dt.items;
  if (!items?.length) return null;

  for (let i = 0; i < items.length; i += 1) {
    const item = items[i];
    if (item.kind !== "file") continue;

    if (typeof (item as DataTransferItemWithHandle).getAsFileSystemHandle === "function") {
      try {
        const fsHandle = await (item as DataTransferItemWithHandle).getAsFileSystemHandle!();
        if (fsHandle.kind === "file") {
          const fileHandle = fsHandle as FileSystemFileHandle;
          const file = await fileHandle.getFile();
          if (isFboxFileName(file.name)) {
            return { handle: fileHandle, file };
          }
        }
      } catch {
        // fall through to getAsFile
      }
    }

    const file = item.getAsFile();
    if (file && isFboxFileName(file.name)) {
      return { handle: null, file };
    }
  }
  return null;
}

/** 节流（默认 2000ms），用于无感自动保存。 */
export function throttle<T extends (...args: never[]) => void>(
  fn: T,
  waitMs: number,
): T & { flush: () => void; cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | null = null;
  let pending = false;

  const invoke = () => {
    timer = null;
    if (pending) {
      pending = false;
      fn();
    }
  };

  const throttled = (() => {
    pending = true;
    if (!timer) {
      timer = setTimeout(invoke, waitMs);
    }
  }) as T & { flush: () => void; cancel: () => void };

  throttled.flush = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    if (pending) {
      pending = false;
      fn();
    }
  };

  throttled.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    pending = false;
  };

  return throttled;
}
