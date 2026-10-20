import type { Row } from "@/lib/step1-rows";
import type { WorkflowStage } from "@/lib/workflow-invalidation";

/** 会改变排箱 / 箱规 / 数量的 Step 1 字段 → 从录入起整条下游过期。 */
export const BOXING_INPUT_FIELDS = [
  "sku",
  "totalQty",
  "perBox",
  "l",
  "w",
  "h",
  "unitKg",
  "emptyKg",
  "grossKg",
] as const satisfies readonly (keyof Row)[];

/**
 * Step 1 单元格变更应失效的起点。
 * FNSKU 不影响排箱，只需要重出 STA / 发货表。
 */
export function stageInvalidatedByInputField(key: keyof Row): WorkflowStage {
  if (key === "fnsku" || key === "dataSource") return "export";
  return "input";
}

export function shouldUnlockBoxingOnInputField(key: keyof Row): boolean {
  return (BOXING_INPUT_FIELDS as readonly string[]).includes(key);
}
