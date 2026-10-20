export interface WarehouseWarning {
  shipment_id: string;
  csv_code: string;
  pdf_code: string;
  message?: string;
}

export type WarehouseChoice = "csv" | "pdf";

function isSubtotal(row: Record<string, unknown>): boolean {
  if (row._subtotal) return true;
  return String(row["仓库代码"] ?? "").includes("小计");
}

/** 采用 CSV 或 PDF 后，货代表明细行的仓码跟着变。选择记在行上，随任务快照保存。 */
export function applyWarehouseChoice(
  rows: Record<string, unknown>[],
  warning: WarehouseWarning,
  choice: WarehouseChoice,
): Record<string, unknown>[] {
  const next = choice === "pdf" ? warning.pdf_code : warning.csv_code;
  const codes = new Set([warning.csv_code, warning.pdf_code]);
  return rows.map((row) => {
    if (isSubtotal(row)) return row;
    const code = String(row["仓库代码"] ?? "");
    if (!codes.has(code)) return row;
    return { ...row, 仓库代码: next, _warehouse_choice: choice };
  });
}
