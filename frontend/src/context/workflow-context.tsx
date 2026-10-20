import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import type { CustomsPackageData, CustomsSource } from "@/lib/api/customs";
import type { ShipmentInvoiceSession } from "@/lib/invoice-session";
import type {
  BoxEditorApiRow,
  BoxMetricRow,
  InvoiceDraftResponse,
  ShipmentBundle,
  TailPoolRow,
} from "@/lib/api/workflow";
import type { ActualPlacementFee } from "@/lib/api/step1";
import { DEFAULT_THROW_RATIO, DEFAULT_WEIGHT_LIMIT_KG } from "@/constants";
import { fetchConfigLimits } from "@/lib/api/workflow";
import { saveTaskHistory } from "@/lib/api/task-history";
import { EMPTY_ROW, type Row } from "@/lib/step1-rows";
import {
  applyTaskHistorySnapshot,
  buildTaskHistorySnapshot,
  newTaskId,
  workflowHasData,
  type WorkflowSnapshotSource,
} from "@/lib/task-history-snapshot";
import {
  autoTaskName,
  clearWorkflowSnapshot,
  loadWorkflowSnapshot,
  resolveRestorableStep,
  saveWorkflowSnapshot,
  snapshotHasData,
  STORAGE_VERSION,
  type WorkflowSnapshot,
} from "@/lib/workflow-storage";
import {
  buildFboxFromSource,
  createEmptyFbox,
  isFileSystemAccessSupported,
  parseFboxText,
  pickSaveNewFbox,
  readFboxFromHandle,
  throttle,
  writeFboxToHandle,
  type FboxSaveStatus,
} from "@/lib/fbox-file-manager";
import {
  clearStoredProjectHandle,
  loadStoredProjectHandle,
  storeProjectHandle,
} from "@/lib/fbox-handle-store";
import {
  clearStaleFrom,
  createEmptyStaleness,
  effectiveStaleness,
  invalidateFrom,
  clearStageStale,
  type WorkflowStage,
  type WorkflowStaleness,
} from "@/lib/workflow-invalidation";
import { saveTaskFileAfterHistory } from "@/lib/task-save-feedback";
import { inferHighestReached } from "@/lib/workflow-steps";

interface WorkflowContextValue {
  step: number;
  setStep: Dispatch<SetStateAction<number>>;
  taskName: string;
  setTaskName: Dispatch<SetStateAction<string>>;
  showRestoredToast: boolean;
  dismissRestoredToast: () => void;
  showArchivedToast: boolean;
  archivedTaskName: string | null;
  dismissArchivedToast: () => void;

  taskId: string;

  inputRows: Row[];
  setInputRows: Dispatch<SetStateAction<Row[]>>;
  fnskuOverrides: Record<string, string>;
  setFnskuOverrides: Dispatch<SetStateAction<Record<string, string>>>;

  boxEditorApi: BoxEditorApiRow[];
  setBoxEditorApi: (rows: BoxEditorApiRow[]) => void;
  metrics: BoxMetricRow[];
  setMetrics: (rows: BoxMetricRow[]) => void;
  tailPool: TailPoolRow[];
  setTailPool: (rows: TailPoolRow[]) => void;
  hasOverweight: boolean;
  setHasOverweight: (v: boolean) => void;
  boxLocked: boolean;
  setBoxLocked: (v: boolean) => void;
  weightLimitKg: number;
  throwRatio: number;
  setThrowRatio: (v: number) => void;
  refreshConfigLimits: () => Promise<void>;

  step3Matrix: Record<string, unknown>[];
  setStep3Matrix: (m: Record<string, unknown>[]) => void;
  step3BoxCount: number;
  setStep3BoxCount: (n: number) => void;
  step3SkuCount: number;
  setStep3SkuCount: (n: number) => void;

  csvFiles: File[];
  setCsvFiles: Dispatch<SetStateAction<File[]>>;
  pdfFiles: File[];
  setPdfFiles: Dispatch<SetStateAction<File[]>>;
  step4Ok: boolean;
  setStep4Ok: (v: boolean) => void;
  step4StatusLines: string[];
  setStep4StatusLines: (lines: string[]) => void;
  step4Errors: string[];
  setStep4Errors: (lines: string[]) => void;
  workerPackingPreview: Record<string, unknown>[];
  setWorkerPackingPreview: (rows: Record<string, unknown>[]) => void;
  workerPackingWarehouses: string[];
  setWorkerPackingWarehouses: (labels: string[]) => void;
  forwarder: Record<string, unknown>[];
  setForwarder: (rows: Record<string, unknown>[]) => void;
  shippingSheet: Record<string, unknown>[];
  setShippingSheet: (rows: Record<string, unknown>[]) => void;
  shippingSheetLegend: Record<string, unknown>[];
  setShippingSheetLegend: (rows: Record<string, unknown>[]) => void;
  shipments: ShipmentBundle[];
  setShipments: (s: ShipmentBundle[]) => void;

  actualPlacementFee: ActualPlacementFee | null;
  setActualPlacementFee: (fee: ActualPlacementFee | null) => void;

  invoiceTemplateBase64: string | null;
  setInvoiceTemplateBase64: (v: string | null) => void;
  invoiceDraft: InvoiceDraftResponse | null;
  setInvoiceDraft: Dispatch<SetStateAction<InvoiceDraftResponse | null>>;
  selectedShipmentId: string;
  setSelectedShipmentId: (id: string) => void;

  invoiceSessionsByShipment: Record<string, ShipmentInvoiceSession>;
  setInvoiceSessionsByShipment: Dispatch<SetStateAction<Record<string, ShipmentInvoiceSession>>>;

  invoiceForwarderId: string;
  setInvoiceForwarderId: Dispatch<SetStateAction<string>>;
  invoicePoByShipment: Record<string, string>;
  setInvoicePoByShipment: Dispatch<SetStateAction<Record<string, string>>>;
  invoiceSyncLinkedEdits: boolean;
  setInvoiceSyncLinkedEdits: Dispatch<SetStateAction<boolean>>;

  customsSession: {
    source: CustomsSource;
    exporterId: string;
    orderNo: string;
    selectedIds: string[];
    data: CustomsPackageData | null;
    previewSig: string;
    activeTab: string;
  } | null;
  setCustomsSession: Dispatch<
    SetStateAction<{
      source: CustomsSource;
      exporterId: string;
      orderNo: string;
      selectedIds: string[];
      data: CustomsPackageData | null;
      previewSig: string;
      activeTab: string;
    } | null>
  >;

  resetWorkflow: () => Promise<void>;
  /** 手动保存当前任务到 .fbox（无绑定文件时弹出另存为） */
  saveTaskToFile: () => Promise<string>;
  saveCurrentTaskToHistory: (name?: string) => Promise<string>;
  loadTaskFromHistory: (snapshot: Record<string, unknown>) => void;

  projectFileName: string | null;
  fboxSaveStatus: FboxSaveStatus;
  fboxWritable: boolean;
  loadFboxFromDrop: (handle: FileSystemFileHandle | null, file: File) => Promise<void>;
  /** Step 4.5 等在存档前将表格最新值刷入快照 */
  registerSnapshotFlush: (fn: () => void) => () => void;

  /** 各阶段下游产物是否因上游变更而过期（已按是否有产物屏蔽） */
  staleness: WorkflowStaleness;
  /** Step 3.5 已保存的刷仓快照数。过期判断只用这个数，不用货代表行数。 */
  setRoutingSnapshotCount: (count: number) => void;
  /** 上游数据变更时标记下游过期（T1 失效链） */
  markStale: (stage: WorkflowStage) => void;
  /** 阶段重算/校验通过后清除该阶段及下游过期标记 */
  clearStaleFrom: (stage: WorkflowStage) => void;
  /** 仅清除单个阶段的过期标记（下游仍保持过期） */
  clearStageStale: (stage: WorkflowStage) => void;
  /** 重置全部过期状态（新建/清空任务时） */
  resetStaleness: () => void;
  /** 本次任务曾经到达的最大步骤（回看用） */
  highestReachedStep: number;
  /** 整表替换（解析/清空）时擦除下游并重置访问水位 */
  resetDownstreamFromInput: () => void;
}

const WorkflowContext = createContext<WorkflowContextValue | null>(null);

export function WorkflowProvider({ children }: { children: ReactNode }) {
  const [hydrated, setHydrated] = useState(false);
  const skipNextSave = useRef(false);
  const skipNextFboxSave = useRef(false);
  const projectFileHandleRef = useRef<FileSystemFileHandle | null>(null);
  const fboxSaveRef = useRef<ReturnType<typeof throttle<() => void>> | null>(null);
  const initProjectRef = useRef(false);

  const [projectFileName, setProjectFileName] = useState<string | null>(null);
  const [fboxSaveStatus, setFboxSaveStatus] = useState<FboxSaveStatus>("idle");
  const [fboxWritable, setFboxWritable] = useState(false);

  const [step, setStep] = useState(1);
  const [taskName, setTaskName] = useState(autoTaskName);
  const [showRestoredToast, setShowRestoredToast] = useState(false);

  const [inputRows, setInputRows] = useState<Row[]>([{ ...EMPTY_ROW }]);
  const [fnskuOverrides, setFnskuOverrides] = useState<Record<string, string>>({});

  const [boxEditorApi, setBoxEditorApi] = useState<BoxEditorApiRow[]>([]);
  const [metrics, setMetrics] = useState<BoxMetricRow[]>([]);
  const [tailPool, setTailPool] = useState<TailPoolRow[]>([]);
  const [hasOverweight, setHasOverweight] = useState(false);
  const [boxLocked, setBoxLocked] = useState(false);
  const [weightLimitKg, setWeightLimitKg] = useState(DEFAULT_WEIGHT_LIMIT_KG);
  const [throwRatio, setThrowRatio] = useState(DEFAULT_THROW_RATIO);

  const [step3Matrix, setStep3Matrix] = useState<Record<string, unknown>[]>([]);
  const [step3BoxCount, setStep3BoxCount] = useState(0);
  const [step3SkuCount, setStep3SkuCount] = useState(0);

  const [csvFiles, setCsvFiles] = useState<File[]>([]);
  const [pdfFiles, setPdfFiles] = useState<File[]>([]);
  const [step4Ok, setStep4Ok] = useState(false);
  const [step4StatusLines, setStep4StatusLines] = useState<string[]>([]);
  const [step4Errors, setStep4Errors] = useState<string[]>([]);
  const [workerPackingPreview, setWorkerPackingPreview] = useState<Record<string, unknown>[]>([]);
  const [workerPackingWarehouses, setWorkerPackingWarehouses] = useState<string[]>([]);
  const [forwarder, setForwarder] = useState<Record<string, unknown>[]>([]);
  const [shippingSheet, setShippingSheet] = useState<Record<string, unknown>[]>([]);
  const [shippingSheetLegend, setShippingSheetLegend] = useState<Record<string, unknown>[]>([]);
  const [shipments, setShipments] = useState<ShipmentBundle[]>([]);
  const [actualPlacementFee, setActualPlacementFee] = useState<ActualPlacementFee | null>(null);

  const [invoiceTemplateBase64, setInvoiceTemplateBase64] = useState<string | null>(null);
  const [invoiceDraft, setInvoiceDraft] = useState<InvoiceDraftResponse | null>(null);
  const [selectedShipmentId, setSelectedShipmentId] = useState("");
  const [invoiceSessionsByShipment, setInvoiceSessionsByShipment] = useState<
    Record<string, ShipmentInvoiceSession>
  >({});
  const [invoiceForwarderId, setInvoiceForwarderId] = useState("");
  const [invoicePoByShipment, setInvoicePoByShipment] = useState<Record<string, string>>({});
  const [invoiceSyncLinkedEdits, setInvoiceSyncLinkedEdits] = useState(true);
  const [customsSession, setCustomsSession] = useState<WorkflowContextValue["customsSession"]>(null);
  const [staleness, setStaleness] = useState<WorkflowStaleness>(() => createEmptyStaleness());
  const [routingSnapshotCount, setRoutingSnapshotCountState] = useState(0);
  const [highestReachedStep, setHighestReachedStep] = useState(1);
  const setRoutingSnapshotCount = useCallback((count: number) => {
    setRoutingSnapshotCountState(count);
  }, []);

  const markStale = useCallback((stage: WorkflowStage) => {
    setStaleness((prev) => invalidateFrom(stage, prev));
  }, []);

  const clearStaleFromStage = useCallback((stage: WorkflowStage) => {
    setStaleness((prev) => clearStaleFrom(stage, prev));
  }, []);

  const clearStageStaleFn = useCallback((stage: WorkflowStage) => {
    setStaleness((prev) => clearStageStale(stage, prev));
  }, []);

  const resetStaleness = useCallback(() => {
    setStaleness(createEmptyStaleness());
  }, []);

  const resetDownstreamFromInput = useCallback(() => {
    setBoxEditorApi([]);
    setMetrics([]);
    setTailPool([]);
    setHasOverweight(false);
    setBoxLocked(false);
    setStep3Matrix([]);
    setStep3BoxCount(0);
    setStep3SkuCount(0);
    setCsvFiles([]);
    setPdfFiles([]);
    setStep4Ok(false);
    setStep4StatusLines([]);
    setStep4Errors([]);
    setWorkerPackingPreview([]);
    setWorkerPackingWarehouses([]);
    setForwarder([]);
    setShippingSheet([]);
    setShippingSheetLegend([]);
    setShipments([]);
    setActualPlacementFee(null);
    setInvoiceTemplateBase64(null);
    setInvoiceDraft(null);
    setSelectedShipmentId("");
    setInvoiceSessionsByShipment({});
    setInvoiceForwarderId("");
    setInvoicePoByShipment({});
    setCustomsSession(null);
    setStaleness(createEmptyStaleness());
    setRoutingSnapshotCountState(0);
    setHighestReachedStep(1);
  }, []);

  const snapshotFlushRef = useRef<(() => void) | null>(null);
  const registerSnapshotFlush = useCallback((fn: () => void) => {
    snapshotFlushRef.current = fn;
    return () => {
      if (snapshotFlushRef.current === fn) snapshotFlushRef.current = null;
    };
  }, []);

  const flushSnapshotPending = useCallback(() => {
    snapshotFlushRef.current?.();
  }, []);

  const [taskId, setTaskId] = useState(() => newTaskId());
  const [showArchivedToast, setShowArchivedToast] = useState(false);
  const [archivedTaskName, setArchivedTaskName] = useState<string | null>(null);

  const dismissRestoredToast = useCallback(() => setShowRestoredToast(false), []);
  const dismissArchivedToast = useCallback(() => setShowArchivedToast(false), []);

  const restoreLocalStorageDraft = useCallback(() => {
    const snapshot = loadWorkflowSnapshot();
    if (!snapshot || !snapshotHasData(snapshot)) return;
    const { step: resolvedStep, clamped } = resolveRestorableStep(snapshot);
    setTaskId(snapshot.taskId || newTaskId());
    setInputRows(snapshot.inputRows);
    setFnskuOverrides(snapshot.fnskuOverrides);
    setBoxEditorApi(snapshot.boxEditorApi);
    setBoxLocked(snapshot.boxLocked);
    setStep(resolvedStep);
    setTaskName(snapshot.taskName);
    setStep4Ok(Boolean(snapshot.step4Ok));
    setStep3Matrix(snapshot.step3Matrix ?? []);
    setStep3BoxCount(snapshot.step3BoxCount ?? 0);
    setStep3SkuCount(snapshot.step3SkuCount ?? 0);
    const reached = inferHighestReached({
      step: resolvedStep,
      highestReachedStep: snapshot.highestReachedStep,
      boxLocked: snapshot.boxLocked,
      step4Ok: Boolean(snapshot.step4Ok),
    });
    setHighestReachedStep(reached);
    if (clamped && !snapshot.step4Ok) {
      setStaleness(invalidateFrom("export", snapshot.staleness ?? createEmptyStaleness()));
    } else {
      setStaleness(snapshot.staleness ?? createEmptyStaleness());
    }
    setShowRestoredToast(true);
  }, []);

  const bindProjectHandle = useCallback(async (handle: FileSystemFileHandle, name: string) => {
    projectFileHandleRef.current = handle;
    setProjectFileName(name);
    setFboxWritable(true);
    setFboxSaveStatus("saved");
    await storeProjectHandle(handle);
  }, []);

  const snapshotSourceRef = useRef<WorkflowSnapshotSource>({
    taskId,
    taskName,
    step,
    inputRows,
    fnskuOverrides,
    boxEditorApi,
    boxLocked,
    throwRatio,
    step3Matrix,
    step3BoxCount,
    step3SkuCount,
    metrics,
    tailPool,
    hasOverweight,
    step4Ok,
    step4StatusLines,
    step4Errors,
    workerPackingPreview,
    workerPackingWarehouses,
    forwarder,
    shippingSheet,
    shippingSheetLegend,
    shipments,
    actualPlacementFee,
    selectedShipmentId,
    invoiceDraft,
    invoiceTemplateBase64,
    invoiceSessionsByShipment,
    invoiceForwarderId,
    invoicePoByShipment,
    invoiceSyncLinkedEdits,
    customsSession,
    highestReachedStep,
    staleness,
  });

  snapshotSourceRef.current = {
    taskId,
    taskName,
    step,
    inputRows,
    fnskuOverrides,
    boxEditorApi,
    boxLocked,
    throwRatio,
    step3Matrix,
    step3BoxCount,
    step3SkuCount,
    metrics,
    tailPool,
    hasOverweight,
    step4Ok,
    step4StatusLines,
    step4Errors,
    workerPackingPreview,
    workerPackingWarehouses,
    forwarder,
    shippingSheet,
    shippingSheetLegend,
    shipments,
    actualPlacementFee,
    selectedShipmentId,
    invoiceDraft,
    invoiceTemplateBase64,
    invoiceSessionsByShipment,
    invoiceForwarderId,
    invoicePoByShipment,
    invoiceSyncLinkedEdits,
    customsSession,
    highestReachedStep,
    staleness,
  };

  const clearWorkflowState = useCallback(
    (overrides?: { taskId?: string; taskName?: string }) => {
      skipNextSave.current = true;
      clearWorkflowSnapshot();
      setTaskId(overrides?.taskId ?? newTaskId());
      setStep(1);
      setTaskName(overrides?.taskName ?? autoTaskName());
    setShowRestoredToast(false);
    setInputRows([{ ...EMPTY_ROW }]);
    setFnskuOverrides({});
    setBoxEditorApi([]);
    setMetrics([]);
    setTailPool([]);
    setHasOverweight(false);
    setBoxLocked(false);
    setStep3Matrix([]);
    setStep3BoxCount(0);
    setStep3SkuCount(0);
    setCsvFiles([]);
    setPdfFiles([]);
    setStep4Ok(false);
    setStep4StatusLines([]);
    setStep4Errors([]);
    setWorkerPackingPreview([]);
    setWorkerPackingWarehouses([]);
    setForwarder([]);
    setShippingSheet([]);
    setShippingSheetLegend([]);
    setShipments([]);
    setActualPlacementFee(null);
    setInvoiceTemplateBase64(null);
    setInvoiceDraft(null);
    setSelectedShipmentId("");
    setInvoiceSessionsByShipment({});
    setInvoiceForwarderId("");
    setInvoicePoByShipment({});
    setInvoiceSyncLinkedEdits(true);
    setCustomsSession(null);
    setStaleness(createEmptyStaleness());
    setRoutingSnapshotCountState(0);
    setHighestReachedStep(1);
    },
    [],
  );

  const applyWorkflowSnapshot = useCallback((applied: ReturnType<typeof applyTaskHistorySnapshot>) => {
    setTaskId(applied.taskId);
    setTaskName(applied.taskName || autoTaskName());
    setStep(applied.step);
    setInputRows(applied.inputRows);
    setFnskuOverrides(applied.fnskuOverrides);
    setBoxEditorApi(applied.boxEditorApi);
    setBoxLocked(applied.boxLocked);
    setThrowRatio(applied.throwRatio);
    setStep3Matrix(applied.step3Matrix);
    setStep3BoxCount(applied.step3BoxCount);
    setStep3SkuCount(applied.step3SkuCount);
    setMetrics(applied.metrics);
    setTailPool(applied.tailPool);
    setHasOverweight(applied.hasOverweight);
    setCsvFiles([]);
    setPdfFiles([]);
    setStep4Ok(applied.step4Ok);
    setStep4StatusLines(applied.step4StatusLines);
    setStep4Errors(applied.step4Errors);
    setWorkerPackingPreview(applied.workerPackingPreview);
    setWorkerPackingWarehouses(applied.workerPackingWarehouses);
    setForwarder(applied.forwarder);
    setShippingSheet(applied.shippingSheet);
    setShippingSheetLegend(applied.shippingSheetLegend);
    setShipments(applied.shipments);
    setActualPlacementFee(applied.actualPlacementFee);
    setInvoiceTemplateBase64(applied.invoiceTemplateBase64);
    setInvoiceDraft(applied.invoiceDraft);
    setSelectedShipmentId(applied.selectedShipmentId);
    setInvoiceSessionsByShipment(applied.invoiceSessionsByShipment);
    setInvoiceForwarderId(applied.invoiceForwarderId);
    setInvoicePoByShipment(applied.invoicePoByShipment);
    setInvoiceSyncLinkedEdits(applied.invoiceSyncLinkedEdits);
    setCustomsSession(applied.customsSession);
    setHighestReachedStep(applied.highestReachedStep);
    setStaleness(applied.staleness);
    setShowRestoredToast(false);
    clearWorkflowSnapshot();
  }, []);

  const persistFboxNow = useCallback(async () => {
    const handle = projectFileHandleRef.current;
    if (!handle) return;
    try {
      flushSnapshotPending();
      setFboxSaveStatus("saving");
      await writeFboxToHandle(handle, buildFboxFromSource(snapshotSourceRef.current));
      setFboxSaveStatus("saved");
    } catch {
      setFboxSaveStatus("error");
    }
  }, [flushSnapshotPending]);

  const loadFboxFromDrop = useCallback(
    async (handle: FileSystemFileHandle | null, file: File) => {
      skipNextSave.current = true;
      skipNextFboxSave.current = true;
      fboxSaveRef.current?.cancel();
      const project = parseFboxText(await file.text());
      const applied = applyTaskHistorySnapshot(
        project.grid_data as unknown as Record<string, unknown>,
      );
      applyWorkflowSnapshot(applied);
      setTaskId(project.task_id);
      setTaskName(project.task_name);
      if (project.settings.step != null) setStep(project.settings.step);
      if (project.settings.throw_ratio != null) setThrowRatio(project.settings.throw_ratio);

      if (handle) {
        await bindProjectHandle(handle, handle.name);
      } else {
        projectFileHandleRef.current = null;
        setProjectFileName(file.name);
        setFboxWritable(false);
        setFboxSaveStatus("saved");
        await clearStoredProjectHandle();
      }
    },
    [applyWorkflowSnapshot, bindProjectHandle],
  );

  useEffect(() => {
    fboxSaveRef.current = throttle(() => {
      void persistFboxNow();
    }, 2000);
    return () => {
      fboxSaveRef.current?.cancel();
      fboxSaveRef.current = null;
    };
  }, [persistFboxNow]);

  const saveCurrentTaskToHistory = useCallback(async (name?: string) => {
    flushSnapshotPending();
    const source = snapshotSourceRef.current;
    if (!workflowHasData(source)) {
      throw new Error("当前无有效任务数据，无需存档");
    }
    const res = await saveTaskHistory(buildTaskHistorySnapshot(source), name ?? source.taskName);
    return res.task_name;
  }, [flushSnapshotPending]);

  const loadTaskFromHistory = useCallback(
    (snapshot: Record<string, unknown>) => {
      skipNextSave.current = true;
      skipNextFboxSave.current = true;
      fboxSaveRef.current?.cancel();
      const applied = applyTaskHistorySnapshot(snapshot);
      applyWorkflowSnapshot(applied);
      projectFileHandleRef.current = null;
      setProjectFileName(null);
      setFboxWritable(false);
      setFboxSaveStatus("idle");
      void clearStoredProjectHandle();
    },
    [applyWorkflowSnapshot],
  );

  const createNewProjectFile = useCallback(
    async (suggestedName?: string) => {
      const { handle, name } = await pickSaveNewFbox(suggestedName ?? autoTaskName());
      const newId = newTaskId();
      const newName = name.replace(/\.fbox$/i, "") || autoTaskName();

      skipNextSave.current = true;
      skipNextFboxSave.current = true;
      fboxSaveRef.current?.cancel();

      await writeFboxToHandle(handle, createEmptyFbox(newId, newName));
      await bindProjectHandle(handle, name);
      clearWorkflowState({ taskId: newId, taskName: newName });
      return { handle, name };
    },
    [bindProjectHandle, clearWorkflowState],
  );

  const saveTaskToFile = useCallback(async (): Promise<string> => {
    flushSnapshotPending();
    const source = snapshotSourceRef.current;
    if (!workflowHasData(source)) {
      throw new Error("当前无有效任务数据，请先录入 SKU 或完成排箱后再保存");
    }

    const project = buildFboxFromSource(source);
    setFboxSaveStatus("saving");
    fboxSaveRef.current?.cancel();

    try {
      const savedName = await saveTaskFileAfterHistory({
        saveHistory: () => saveCurrentTaskToHistory(source.taskName),
        writeFile: async () => {
          const handle = projectFileHandleRef.current;
          if (handle && fboxWritable) {
            await writeFboxToHandle(handle, project);
            return projectFileName ?? handle.name;
          }
          const { handle: newHandle, name } = await pickSaveNewFbox(source.taskName || autoTaskName());
          await writeFboxToHandle(newHandle, project);
          await bindProjectHandle(newHandle, name);
          const displayName = name.replace(/\.fbox$/i, "") || source.taskName;
          setTaskName(displayName);
          return name;
        },
      });
      setFboxSaveStatus("saved");
      return savedName;
    } catch (err) {
      if (err instanceof Error && err.message === "已取消保存") {
        setFboxSaveStatus(projectFileHandleRef.current ? "saved" : "idle");
        throw err;
      }
      setFboxSaveStatus("error");
      throw err;
    }
  }, [flushSnapshotPending, bindProjectHandle, fboxWritable, projectFileName, saveCurrentTaskToHistory]);

  const resetWorkflow = useCallback(async () => {
    const source = snapshotSourceRef.current;
    if (workflowHasData(source)) {
      try {
        const savedName = await saveCurrentTaskToHistory(source.taskName);
        setArchivedTaskName(savedName);
        setShowArchivedToast(true);
      } catch {
        // 存档失败不阻断重新开始
      }
    }

    try {
      await createNewProjectFile(autoTaskName());
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      if (err instanceof DOMException && err.name === "SecurityError") return;
      throw err;
    }
  }, [createNewProjectFile, saveCurrentTaskToHistory]);

  useEffect(() => {
    fetchConfigLimits()
      .then((cfg) => {
        setWeightLimitKg(cfg.weight_limit_kg);
        setThrowRatio(cfg.throw_ratio);
      })
      .catch(() => undefined);
  }, []);

  const refreshConfigLimits = useCallback(async () => {
    const cfg = await fetchConfigLimits();
    setWeightLimitKg(cfg.weight_limit_kg);
    setThrowRatio(cfg.throw_ratio);
  }, []);

  useEffect(() => {
    setHydrated(true);
  }, []);

  useEffect(() => {
    setHighestReachedStep((h) => (step > h ? step : h));
  }, [step]);

  useEffect(() => {
    if (!hydrated || initProjectRef.current) return;
    initProjectRef.current = true;
    let cancelled = false;

    void (async () => {
      if (!isFileSystemAccessSupported()) {
        if (!cancelled) restoreLocalStorageDraft();
        return;
      }

      try {
        const storedHandle = await loadStoredProjectHandle();
        if (cancelled) return;
        if (storedHandle) {
          skipNextSave.current = true;
          skipNextFboxSave.current = true;
          const project = await readFboxFromHandle(storedHandle);
          if (cancelled) return;
          const applied = applyTaskHistorySnapshot(
            project.grid_data as unknown as Record<string, unknown>,
          );
          applyWorkflowSnapshot(applied);
          setTaskId(project.task_id);
          setTaskName(project.task_name);
          if (project.settings.step != null) setStep(project.settings.step);
          if (project.settings.throw_ratio != null) setThrowRatio(project.settings.throw_ratio);
          await bindProjectHandle(storedHandle, storedHandle.name);
          return;
        }
      } catch {
        await clearStoredProjectHandle();
      }

      if (cancelled) return;

      // 无已绑定 .fbox 时不自动弹出保存对话框（浏览器要求用户手势，否则 SecurityError 白屏）
      restoreLocalStorageDraft();
    })();

    return () => {
      cancelled = true;
    };
  }, [
    hydrated,
    applyWorkflowSnapshot,
    bindProjectHandle,
    restoreLocalStorageDraft,
  ]);

  useEffect(() => {
    if (!hydrated) return;

    if (skipNextSave.current) {
      skipNextSave.current = false;
      return;
    }

    const timer = window.setTimeout(() => {
      const snapshot: WorkflowSnapshot = {
        version: STORAGE_VERSION,
        savedAt: new Date().toISOString(),
        taskId,
        taskName,
        step,
        inputRows,
        fnskuOverrides,
        boxEditorApi,
        boxLocked,
        highestReachedStep,
        step4Ok,
        staleness,
        step3Matrix,
        step3BoxCount,
        step3SkuCount,
      };
      if (snapshotHasData(snapshot)) {
        saveWorkflowSnapshot(snapshot);
      } else {
        clearWorkflowSnapshot();
      }
    }, 600);

    return () => window.clearTimeout(timer);
  }, [
    hydrated,
    taskId,
    taskName,
    step,
    inputRows,
    fnskuOverrides,
    boxEditorApi,
    boxLocked,
    highestReachedStep,
    step4Ok,
    staleness,
    step3Matrix,
    step3BoxCount,
    step3SkuCount,
  ]);

  useEffect(() => {
    if (!hydrated || !fboxWritable || !projectFileHandleRef.current) return;
    if (skipNextFboxSave.current) {
      skipNextFboxSave.current = false;
      return;
    }
    fboxSaveRef.current?.();
  }, [
    hydrated,
    fboxWritable,
    taskId,
    taskName,
    step,
    inputRows,
    fnskuOverrides,
    boxEditorApi,
    boxLocked,
    throwRatio,
    step3Matrix,
    step3BoxCount,
    step3SkuCount,
    metrics,
    tailPool,
    hasOverweight,
    step4Ok,
    step4StatusLines,
    step4Errors,
    workerPackingPreview,
    workerPackingWarehouses,
    forwarder,
    shippingSheet,
    shippingSheetLegend,
    shipments,
    actualPlacementFee,
    invoiceTemplateBase64,
      invoiceDraft,
      selectedShipmentId,
      invoiceSessionsByShipment,
      invoiceForwarderId,
      invoicePoByShipment,
      invoiceSyncLinkedEdits,
      customsSession,
      highestReachedStep,
      staleness,
  ]);

  const visibleStaleness = useMemo(
    () =>
      effectiveStaleness(staleness, {
        boxEditorCount: boxEditorApi.length,
        step3MatrixCount: step3Matrix.length,
        routingSnapshotCount,
        step4Ok,
        step4StatusLineCount: step4StatusLines.length,
        hasInvoiceDraft: invoiceDraft != null,
        invoiceSessionCount: Object.keys(invoiceSessionsByShipment).length,
        hasCustomsSession: customsSession != null,
      }),
    [
      staleness,
      boxEditorApi.length,
      step3Matrix.length,
      routingSnapshotCount,
      step4Ok,
      step4StatusLines.length,
      invoiceDraft,
      invoiceSessionsByShipment,
      customsSession,
    ],
  );

  const value = useMemo(
    () => ({
      step,
      setStep,
      taskName,
      setTaskName,
      showRestoredToast,
      dismissRestoredToast,
      showArchivedToast,
      archivedTaskName,
      dismissArchivedToast,
      taskId,
      inputRows,
      setInputRows,
      fnskuOverrides,
      setFnskuOverrides,
      boxEditorApi,
      setBoxEditorApi,
      metrics,
      setMetrics,
      tailPool,
      setTailPool,
      hasOverweight,
      setHasOverweight,
      boxLocked,
      setBoxLocked,
      weightLimitKg,
      throwRatio,
      setThrowRatio,
      refreshConfigLimits,
      step3Matrix,
      setStep3Matrix,
      step3BoxCount,
      setStep3BoxCount,
      step3SkuCount,
      setStep3SkuCount,
      csvFiles,
      setCsvFiles,
      pdfFiles,
      setPdfFiles,
      step4Ok,
      setStep4Ok,
      step4StatusLines,
      setStep4StatusLines,
      step4Errors,
      setStep4Errors,
      workerPackingPreview,
      setWorkerPackingPreview,
      workerPackingWarehouses,
      setWorkerPackingWarehouses,
      forwarder,
      setForwarder,
      shippingSheet,
      setShippingSheet,
      shippingSheetLegend,
      setShippingSheetLegend,
      shipments,
      setShipments,
      actualPlacementFee,
      setActualPlacementFee,
      invoiceTemplateBase64,
      setInvoiceTemplateBase64,
      invoiceDraft,
      setInvoiceDraft,
      selectedShipmentId,
      setSelectedShipmentId,
      invoiceSessionsByShipment,
      setInvoiceSessionsByShipment,
      invoiceForwarderId,
      setInvoiceForwarderId,
      invoicePoByShipment,
      setInvoicePoByShipment,
      invoiceSyncLinkedEdits,
      setInvoiceSyncLinkedEdits,
      customsSession,
      setCustomsSession,
      resetWorkflow,
      saveTaskToFile,
      saveCurrentTaskToHistory,
      loadTaskFromHistory,
      projectFileName,
      fboxSaveStatus,
      fboxWritable,
      loadFboxFromDrop,
      registerSnapshotFlush,
      staleness: visibleStaleness,
      setRoutingSnapshotCount,
      markStale,
      clearStaleFrom: clearStaleFromStage,
      clearStageStale: clearStageStaleFn,
      resetStaleness,
      highestReachedStep,
      resetDownstreamFromInput,
    }),
    [
      step,
      taskName,
      taskId,
      visibleStaleness,
      setRoutingSnapshotCount,
      markStale,
      clearStaleFromStage,
      clearStageStaleFn,
      resetStaleness,
      highestReachedStep,
      resetDownstreamFromInput,
      showRestoredToast,
      dismissRestoredToast,
      showArchivedToast,
      archivedTaskName,
      dismissArchivedToast,
      inputRows,
      fnskuOverrides,
      boxEditorApi,
      metrics,
      tailPool,
      hasOverweight,
      boxLocked,
      weightLimitKg,
      throwRatio,
      refreshConfigLimits,
      step3Matrix,
      step3BoxCount,
      step3SkuCount,
      csvFiles,
      pdfFiles,
      step4Ok,
      step4StatusLines,
      step4Errors,
      workerPackingPreview,
      workerPackingWarehouses,
      forwarder,
      shippingSheet,
      shippingSheetLegend,
      shipments,
      actualPlacementFee,
      invoiceTemplateBase64,
      invoiceDraft,
      selectedShipmentId,
      invoiceSessionsByShipment,
      invoiceForwarderId,
      invoicePoByShipment,
      invoiceSyncLinkedEdits,
      customsSession,
      resetWorkflow,
      saveTaskToFile,
      saveCurrentTaskToHistory,
      loadTaskFromHistory,
      projectFileName,
      fboxSaveStatus,
      fboxWritable,
      loadFboxFromDrop,
      registerSnapshotFlush,
    ],
  );

  return <WorkflowContext.Provider value={value}>{children}</WorkflowContext.Provider>;
}

export function useWorkflow() {
  const ctx = useContext(WorkflowContext);
  if (!ctx) throw new Error("useWorkflow must be used within WorkflowProvider");
  return ctx;
}
