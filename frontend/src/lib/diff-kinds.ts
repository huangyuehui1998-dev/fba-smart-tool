/** 领星同步差异的中文名和需要醒目（琥珀色）显示的种类。S9-step4。 */
export const DIFF_LABEL: Record<string, string> = {
  applied: "已写入",
  locked: "手填锁定",
  needs_review: "待人工确认",
  retry: "失败重试",
  error: "错误",
  permission: "权限",
  skip_platform: "非 Amazon",
  price_invalid: "价格无效",
  row_skipped: "跳过该行",
  sku_mismatch: "SKU 与本地不一致",
  sku_case_conflict: "SKU 只差大小写",
  price_history_missing: "无促销前历史价",
};

/** 这些差异用琥珀色显示（需要人看一眼） */
export const AMBER_DIFF_KINDS = new Set(["price_history_missing", "sku_case_conflict", "price_invalid"]);

export function diffItemClass(kind: string): string {
  return AMBER_DIFF_KINDS.has(kind) ? "rounded bg-amber-50 px-1 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200" : "";
}
