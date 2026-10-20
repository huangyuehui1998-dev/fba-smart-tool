/**
 * 工作流步骤定义与导航门禁。
 *
 * 已访问过的步骤可随时回看（数据保留，过期仅禁止当正式稿）。
 * 从未做过的步骤仍需满足前置条件。
 */
import type { BoxEditorApiRow } from "@/lib/api/workflow";
import type { Row } from "@/lib/step1-rows";

export const WORKFLOW_STEPS = [
  { id: 1, label: "Step 1 录入" },
  { id: 2, label: "Step 2 排箱" },
  { id: 3, label: "Step 3 导出" },
  { id: 3.5, label: "Step 3.5 刷仓" },
  { id: 4, label: "Step 4 回传校验" },
  { id: 4.5, label: "Step 4.5 发票" },
  { id: 5, label: "Step 5 报关" },
] as const;

export type WorkflowStepId = (typeof WORKFLOW_STEPS)[number]["id"];

export interface StepGuardState {
  inputRows: Row[];
  boxLocked: boolean;
  boxEditorApi: BoxEditorApiRow[];
  step4Ok: boolean;
  /** 本次任务曾经到达过的最大步骤（回看用，不因过期而回退）。 */
  highestReachedStep: number;
}

export function hasValidInputRows(rows: Row[]): boolean {
  return rows.some((r) => r.sku.trim() && Number(r.totalQty) > 0);
}

export function hasLockedBoxPlan(state: StepGuardState): boolean {
  return state.boxLocked && state.boxEditorApi.length > 0;
}

export function inferHighestReached(args: {
  step: number;
  highestReachedStep?: number;
  boxLocked: boolean;
  step4Ok: boolean;
  hasInvoice?: boolean;
  hasCustoms?: boolean;
}): number {
  const saved = args.highestReachedStep ?? 0;
  let h = Math.max(1, saved);
  const step = args.step || 1;
  if (step <= 3) {
    h = Math.max(h, step);
  } else if (saved >= step || args.step4Ok || args.hasInvoice || args.hasCustoms) {
    h = Math.max(h, step);
  }
  if (args.boxLocked) h = Math.max(h, 3);
  if (args.step4Ok) h = Math.max(h, 4);
  if (args.hasInvoice) h = Math.max(h, 4.5);
  if (args.hasCustoms) h = Math.max(h, 5);
  return h;
}

function isRevisit(targetStep: number, highestReachedStep: number): boolean {
  return targetStep <= highestReachedStep;
}

/** 是否允许从 currentStep 跳转到 targetStep（允许回退、回看已访问步骤）。 */
export function canEnterStep(
  targetStep: number,
  currentStep: number,
  state: StepGuardState,
): boolean {
  if (targetStep === currentStep) return true;
  if (targetStep < currentStep) return true;
  if (isRevisit(targetStep, state.highestReachedStep)) return true;

  if (targetStep >= 2 && !hasValidInputRows(state.inputRows)) return false;
  if (targetStep >= 3 && targetStep < 4.5 && !hasLockedBoxPlan(state)) return false;
  if ((targetStep === 4.5 || targetStep === 5) && !state.step4Ok) return false;

  return true;
}

/** 不可进入时的原因说明（供 tooltip / toast）。 */
export function getStepBlockReason(targetStep: number, state: StepGuardState): string | null {
  if (isRevisit(targetStep, state.highestReachedStep)) return null;

  if (targetStep >= 2 && !hasValidInputRows(state.inputRows)) {
    return "请先在 Step 1 录入至少一条有效 SKU（含发货数量）";
  }
  if (targetStep >= 3 && targetStep < 4.5 && !hasLockedBoxPlan(state)) {
    if (targetStep === 3.5) return "刷仓预览需先锁定装箱方案";
    if (targetStep === 4) return "回传校验需先锁定装箱方案";
    return "请先在 Step 2 完成排箱并锁定方案";
  }
  if ((targetStep === 4.5 || targetStep === 5) && !state.step4Ok) {
    return "请先完成 Step 4 货件校验并通过";
  }
  return null;
}
