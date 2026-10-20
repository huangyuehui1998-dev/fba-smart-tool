export const SHIPPING_SHEET_LEGEND_COLUMNS = [
  "SKU简称",
  "发货总数",
  "单箱装量",
  "箱长(cm)",
  "箱宽(cm)",
  "箱高(cm)",
] as const;

export const SHIPPING_SHEET_LEGEND_LABELS = SHIPPING_SHEET_LEGEND_COLUMNS.map((c) => `${c}*`);

/** Step 1 浅色字段带：SKU 列 colspan，其余字段相对原布局右移 2 列 */
export const SHIPPING_SHEET_LEGEND_SKU_COLSPAN = 3;

export const SHIPPING_SHEET_COLUMNS = [
  "票数",
  "仓库代码",
  "FBA货件编号",
  "箱号",
  "亚马逊条码(FNSKU)",
  "中文品名",
  "总数量",
  "总毛重(KG)",
  "外箱长(CM)",
  "外箱宽(CM)",
  "外箱高(CM)",
  "单箱体积(CBM)",
] as const;

const HEADER_LABELS: Record<string, [string, string]> = {
  票数: ["票数", "Ticket"],
  仓库代码: ["仓库代码", "Warehouse"],
  FBA货件编号: ["FBA 货件编号", "Shipment ID"],
  箱号: ["箱号", "Carton No."],
  "亚马逊条码(FNSKU)": ["亚马逊条码", "FNSKU"],
  中文品名: ["中文品名", "CN Name"],
  总数量: ["总数量", "Total Qty"],
  "总毛重(KG)": ["总毛重(KG)", "Total G.W."],
  "外箱长(CM)": ["外箱长(CM)", "Length"],
  "外箱宽(CM)": ["外箱宽(CM)", "Width"],
  "外箱高(CM)": ["外箱高(CM)", "Height"],
  "单箱体积(CBM)": ["单箱体积(CBM)", "Volume"],
};

const NUMERIC_COLS = new Set([
  "总数量",
  "总毛重(KG)",
  "外箱长(CM)",
  "外箱宽(CM)",
  "外箱高(CM)",
  "单箱体积(CBM)",
]);

export type ShippingSheetRow = Record<string, unknown>;

export function shippingSheetHeaderLabel(col: string): { cn: string; en: string } {
  const [cn, en] = HEADER_LABELS[col] ?? [col, ""];
  return { cn, en };
}

export function isShippingSheetNumericColumn(col: string): boolean {
  return NUMERIC_COLS.has(col);
}

export type ShippingSheetLegendRow = Record<string, unknown>;

export function formatShippingSheetLegendCell(col: string, row: ShippingSheetLegendRow): string {
  const raw = row[col];
  if (raw === null || raw === undefined || raw === "") return "";
  if (col === "发货总数" || col === "单箱装量") return String(Math.round(Number(raw)));
  if (col === "箱长(cm)" || col === "箱宽(cm)" || col === "箱高(cm)") {
    return Number(raw).toFixed(1);
  }
  return String(raw);
}

export function formatShippingSheetCell(col: string, row: ShippingSheetRow): string {
  const raw = row[col];
  if (raw === null || raw === undefined || raw === "") return "";
  if (col === "总数量") return String(Math.round(Number(raw)));
  if (col === "总毛重(KG)") return Number(raw).toFixed(2);
  if (col === "单箱体积(CBM)") return Number(raw).toFixed(3);
  if (col === "外箱长(CM)" || col === "外箱宽(CM)" || col === "外箱高(CM)") {
    return Number(raw).toFixed(1);
  }
  return String(raw);
}

export function shippingSheetColumns(rows: ShippingSheetRow[]): string[] {
  if (!rows.length) return [...SHIPPING_SHEET_COLUMNS];
  const fromData = Object.keys(rows[0]);
  const ordered = SHIPPING_SHEET_COLUMNS.filter((c) => fromData.includes(c));
  const extras = fromData.filter((c) => !(ordered as string[]).includes(c));
  return [...ordered, ...extras];
}
