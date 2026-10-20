/**
 * 工作流下游失效链 — 上游数据变更时标记下游产物为「已过期」。
 *
 * 语义：标记过期 ≠ 清空数据。旧结果保留供用户对照，UI 提示需重算/重新校验。
 */

/** 工作流各阶段，与步骤一一对应（routing 为 Step 3.5 独立分支）。 */
export type WorkflowStage =
  | "input"
  | "boxing"
  | "export"
  | "routing"
  | "validation"
  | "invoice"
  | "customs";

/** 各阶段过期状态。true = 上游已变更，当前阶段产物不可信。 */
export type WorkflowStaleness = Record<WorkflowStage, boolean>;

/** 阶段顺序：invalidateFrom(stage) 会将 stage 之后的所有阶段标记为过期。 */
export const STAGE_ORDER: readonly WorkflowStage[] = [
  "input",
  "boxing",
  "export",
  "routing",
  "validation",
  "invoice",
  "customs",
] as const;

/** 阶段 → 用户可见中文标签（供 UI 提示）。 */
export const STAGE_LABELS: Record<WorkflowStage, string> = {
  input: "Step 1 录入",
  boxing: "Step 2 排箱",
  export: "Step 3 导出",
  routing: "Step 3.5 刷仓",
  validation: "Step 4 回传校验",
  invoice: "Step 4.5 发票",
  customs: "Step 5 报关",
};

export function createEmptyStaleness(): WorkflowStaleness {
  return {
    input: false,
    boxing: false,
    export: false,
    routing: false,
    validation: false,
    invoice: false,
    customs: false,
  };
}

/**
 * 从指定阶段起，将其所有下游阶段标记为过期。
 * @param stage 发生变更的上游阶段
 * @param current 当前过期状态（可选，默认全 false）
 */
export function invalidateFrom(
  stage: WorkflowStage,
  current: WorkflowStaleness = createEmptyStaleness(),
): WorkflowStaleness {
  const idx = STAGE_ORDER.indexOf(stage);
  if (idx === -1) return { ...current };

  const next = { ...current };
  for (let i = idx + 1; i < STAGE_ORDER.length; i++) {
    next[STAGE_ORDER[i]] = true;
  }
  return next;
}

/**
 * 清除单个阶段的过期标记（该阶段重算/校验成功后调用，不影响下游过期状态）。
 */
export function clearStageStale(stage: WorkflowStage, current: WorkflowStaleness): WorkflowStaleness {
  return { ...current, [stage]: false };
}

/**
 * 从指定阶段起，清除该阶段及所有下游的过期标记（整条下游链已刷新时调用）。
 */
export function clearStaleFrom(stage: WorkflowStage, current: WorkflowStaleness): WorkflowStaleness {
  const idx = STAGE_ORDER.indexOf(stage);
  if (idx === -1) return { ...current };

  const next = { ...current };
  for (let i = idx; i < STAGE_ORDER.length; i++) {
    next[STAGE_ORDER[i]] = false;
  }
  return next;
}

/** 是否存在任一过期阶段。 */
export function hasAnyStale(staleness: WorkflowStaleness, stages?: readonly WorkflowStage[]): boolean {
  const check = stages ?? STAGE_ORDER;
  return check.some((s) => staleness[s]);
}

/** 返回所有过期阶段的中文标签列表。 */
export function getStaleStageLabels(staleness: WorkflowStaleness): string[] {
  return STAGE_ORDER.filter((s) => staleness[s]).map((s) => STAGE_LABELS[s]);
}

/** 某 UI 步骤是否处于过期状态。 */
export function isStepStale(step: number, staleness: WorkflowStaleness): boolean {
  switch (step) {
    case 1:
      return false;
    case 2:
      return staleness.boxing;
    case 3:
      return staleness.export;
    case 3.5:
      return staleness.routing;
    case 4:
      return staleness.validation;
    case 4.5:
      return staleness.invoice;
    case 5:
      return staleness.customs;
    default:
      return false;
  }
}

/** 各阶段对应的正式导出文件（过期后不得当现行稿发出）。 */
export const OFFICIAL_FILES_BY_STAGE: Record<WorkflowStage, readonly string[]> = {
  input: [],
  boxing: [],
  export: ["内部留档表", "Send to Amazon 模板"],
  routing: ["刷仓货代表"],
  validation: ["工人装箱贴标实操单", "发货表", "货代表", "热敏箱唛"],
  invoice: ["货代发票"],
  customs: ["报关资料"],
};

export const STALE_DOWNLOAD_HINT =
  "当前结果已过期，不能作为正式文件下载。请按步骤重新计算或校验后再导出。";

export function isOfficialExportBlocked(
  stage: WorkflowStage,
  staleness: WorkflowStaleness,
): boolean {
  return Boolean(staleness[stage]);
}

export function getOfficialFilesForStage(stage: WorkflowStage): string[] {
  return [...OFFICIAL_FILES_BY_STAGE[stage]];
}

/** 所有过期阶段上的正式文件（去重，供横幅列出「需重出」）。 */
export function getStaleOfficialFileLabels(staleness: WorkflowStaleness): string[] {
  const seen = new Set<string>();
  const labels: string[] = [];
  for (const stage of STAGE_ORDER) {
    if (!staleness[stage]) continue;
    for (const name of OFFICIAL_FILES_BY_STAGE[stage]) {
      if (seen.has(name)) continue;
      seen.add(name);
      labels.push(name);
    }
  }
  return labels;
}

export function parseStaleness(raw: unknown): WorkflowStaleness {
  const empty = createEmptyStaleness();
  if (!raw || typeof raw !== "object") return empty;
  const rec = raw as Record<string, unknown>;
  const next = { ...empty };
  for (const stage of STAGE_ORDER) {
    next[stage] = Boolean(rec[stage]);
  }
  return next;
}
