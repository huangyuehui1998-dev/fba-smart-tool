/**
 * 工作流步骤定义与导航门禁。
 *
 * 已访问过的步骤可随时回看（数据保留，过期仅禁止当正式稿）。
 * 从未做过的步骤仍需满足前置条件。
 */
import type { BoxEditorApiRow } from "@/lib/api/workflow";
import type { Row } from "@/lib/step1-rows";

export const WORKFLOW_STEPS = [
  { id: 1, label: "1 录入" },
  { id: 2, label: "2 排箱" },
  { id: 3, label: "3 导出" },
  { id: 4, label: "4 货件校验" },
  { id: 4.5, label: "5 发票" },
  { id: 5, label: "6 报关" },
  { id: 3.5, label: "7 刷仓" },
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

export interface StepBlockDetail {
  message: string;
  missing: string[];
  jumpTo: number;
}

/** 不可进入时的原因说明（供 tooltip / 对话框）。 */
export function getStepBlockDetail(targetStep: number, state: StepGuardState): StepBlockDetail | null {
  if (isRevisit(targetStep, state.highestReachedStep)) return null;

  if (targetStep >= 2 && !hasValidInputRows(state.inputRows)) {
    return {
      message: "请先完成第 1 步：录入至少一条有效 SKU（含发货数量）",
      missing: ["至少一条 SKU 和发货数量"],
      jumpTo: 1,
    };
  }
  if (targetStep >= 3 && targetStep < 4.5 && !hasLockedBoxPlan(state)) {
    return {
      message: "请先完成第 2 步：排箱并锁定方案",
      missing: ["装箱方案尚未锁定"],
      jumpTo: 2,
    };
  }
  if ((targetStep === 4.5 || targetStep === 5) && !state.step4Ok) {
    return {
      message: "请先完成第 4 步：货件校验",
      missing: ["货件校验尚未通过"],
      jumpTo: 4,
    };
  }
  return null;
}

export function getStepBlockReason(targetStep: number, state: StepGuardState): string | null {
  return getStepBlockDetail(targetStep, state)?.message ?? null;
}
