import type { BoxEditorApiRow } from "@/lib/api/workflow";
import { EMPTY_ROW, type Row } from "@/lib/step1-rows";
import {
  createEmptyStaleness,
  parseStaleness,
  type WorkflowStaleness,
} from "@/lib/workflow-invalidation";
import { inferHighestReached } from "@/lib/workflow-steps";

const STORAGE_KEY = "fba_workflow_autosave";
/** v1 旧草稿仍可读；新写入为 v2。 */
export const STORAGE_VERSION = 2;

export interface WorkflowSnapshot {
  version: 1 | 2;
  savedAt: string;
  taskId: string;
  taskName: string;
  step: number;
  inputRows: Row[];
  fnskuOverrides: Record<string, string>;
  boxEditorApi: BoxEditorApiRow[];
  boxLocked: boolean;
  highestReachedStep?: number;
  step4Ok?: boolean;
  staleness?: WorkflowStaleness;
  step3Matrix?: Record<string, unknown>[];
  step3BoxCount?: number;
  step3SkuCount?: number;
}

export function autoTaskName(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `Task-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
}

export function snapshotHasData(snapshot: WorkflowSnapshot): boolean {
  if (snapshot.boxLocked || snapshot.boxEditorApi.length > 0 || snapshot.step4Ok) return true;
  return snapshot.inputRows.some((r) => r.sku.trim());
}

export function loadWorkflowSnapshot(): WorkflowSnapshot | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw) as WorkflowSnapshot;
    if (data.version !== 1 && data.version !== 2) return null;
    return {
      ...data,
      highestReachedStep: data.highestReachedStep,
      step4Ok: Boolean(data.step4Ok),
      staleness: parseStaleness(data.staleness),
      step3Matrix: Array.isArray(data.step3Matrix) ? data.step3Matrix : [],
      step3BoxCount: Number(data.step3BoxCount ?? 0),
      step3SkuCount: Number(data.step3SkuCount ?? 0),
    };
  } catch {
    return null;
  }
}

export function saveWorkflowSnapshot(snapshot: WorkflowSnapshot): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // quota exceeded — ignore
  }
}

export function clearWorkflowSnapshot(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}

export function createEmptySnapshot(): WorkflowSnapshot {
  return {
    version: STORAGE_VERSION,
    savedAt: new Date().toISOString(),
    taskId: typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `task-${Date.now()}`,
    taskName: autoTaskName(),
    step: 1,
    inputRows: [{ ...EMPTY_ROW }],
    fnskuOverrides: {},
    boxEditorApi: [],
    boxLocked: false,
    highestReachedStep: 1,
    step4Ok: false,
    staleness: createEmptyStaleness(),
    step3Matrix: [],
    step3BoxCount: 0,
    step3SkuCount: 0,
  };
}

/**
 * 恢复步骤：有数据支撑则回到离开时的步骤（含 4/5），而不是一律压回 Step 3。
 * v1 草稿没有 step4Ok 时，仍最多恢复到 Step 3。
 */
export function resolveRestorableStep(snapshot: WorkflowSnapshot): {
  step: number;
  clamped: boolean;
} {
  let maxStep = 1;
  if (snapshot.inputRows.some((r) => r.sku.trim())) {
    maxStep = 2;
  }
  if (snapshot.boxLocked && snapshot.boxEditorApi.length > 0) {
    maxStep = 3;
  }

  const inferred = inferHighestReached({
    step: snapshot.step,
    highestReachedStep: snapshot.highestReachedStep,
    boxLocked: snapshot.boxLocked,
    step4Ok: Boolean(snapshot.step4Ok),
  });

  if (snapshot.step4Ok || inferred >= 4) {
    maxStep = Math.max(maxStep, Math.min(5, inferred), snapshot.step4Ok ? 4 : 0);
  }

  if (snapshot.step === 3.5 && maxStep >= 3) {
    maxStep = Math.max(maxStep, 3.5);
  }

  const step = Math.min(snapshot.step, maxStep);
  return { step, clamped: step !== snapshot.step };
}
