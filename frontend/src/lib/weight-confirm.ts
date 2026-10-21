/** Step1 毛重确认：同一份录入只弹一次，录入变了再弹。 */

export interface WeightConfirmInput {
  sku?: string;
  totalQty?: string;
  perBox?: string;
  unitKg?: string;
  emptyKg?: string;
  grossKg?: string;
  "SKU简称"?: string;
  "发货总数"?: string | number;
  "单箱装量"?: string | number;
  "单个重量(kg)"?: string | number | null;
  "空纸箱重(kg)"?: string | number | null;
  "单箱毛重(kg)"?: string | number | null;
}

function cell(row: WeightConfirmInput, apiKey: keyof WeightConfirmInput, uiKey: keyof WeightConfirmInput): string {
  const value = row[apiKey] ?? row[uiKey];
  return value == null ? "" : String(value).trim();
}

export function weightRowsHash(rows: WeightConfirmInput[]): string {
  return JSON.stringify(
    rows.map((row) => ({
      sku: cell(row, "SKU简称", "sku"),
      total: cell(row, "发货总数", "totalQty"),
      per: cell(row, "单箱装量", "perBox"),
      unit: cell(row, "单个重量(kg)", "unitKg"),
      tare: cell(row, "空纸箱重(kg)", "emptyKg"),
      gross: cell(row, "单箱毛重(kg)", "grossKg"),
    })),
  );
}

export function shouldPromptWeightConfirm(
  rows: WeightConfirmInput[],
  acknowledgedHash: string | null,
  requiresConfirm: boolean,
): boolean {
  if (!requiresConfirm) return false;
  return acknowledgedHash !== weightRowsHash(rows);
}
