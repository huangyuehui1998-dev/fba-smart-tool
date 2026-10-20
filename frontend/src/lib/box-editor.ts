import type { BoxEditorApiRow } from "@/lib/api/workflow";

let _seq = 0;

export interface BoxEditorRow {
  id: string;
  box: number;
  source: "整箱" | "混装";
  sku: string;
  qty: number;
}

export function newBoxRowId(): string {
  _seq += 1;
  return `box-row-${_seq}`;
}

export function apiToBoxEditor(rows: BoxEditorApiRow[]): BoxEditorRow[] {
  return rows.map((r) => ({
    id: newBoxRowId(),
    box: Number(r.箱号) || 0,
    source: r.来源 === "整箱" ? "整箱" : "混装",
    sku: String(r.SKU简称 ?? ""),
    qty: Number(r.数量) || 0,
  }));
}

export function boxEditorToApi(rows: BoxEditorRow[]): BoxEditorApiRow[] {
  return rows.map((r) => ({
    箱号: r.box,
    来源: r.source,
    SKU简称: r.sku,
    数量: r.qty,
  }));
}

export function groupBoxItems(rows: BoxEditorRow[], boxNo: number) {
  return rows
    .filter((r) => r.box === boxNo && r.sku.trim())
    .map((r) => ({ sku: r.sku, qty: r.qty }));
}

export function boxNumbers(rows: BoxEditorRow[]): number[] {
  return [...new Set(rows.map((r) => r.box).filter((n) => n > 0))].sort((a, b) => a - b);
}

export function matrixBoxColumns(matrix: Record<string, unknown>[]): string[] {
  if (!matrix.length) return [];
  return Object.keys(matrix[0]).filter((k) => k !== "SKU简称" && /^第\d+箱$/.test(k));
}

export function horizontalWarehouseColumns(horizontal: Record<string, unknown>[]): string[] {
  if (!horizontal.length) return [];
  const wh = new Set<string>();
  for (const key of Object.keys(horizontal[0])) {
    const m = key.match(/^(.+?)_(?:纸箱编号|产品名称)$/);
    if (m) wh.add(m[1]);
  }
  return [...wh];
}

export function sourceLabelToKind(label: string): "exact" | "local" | "ai" | "missing" | "preview" {
  if (label.includes("模板解析")) return "preview";
  if (label.includes("精准提取")) return "exact";
  if (label.includes("产品信息表") || label.includes("主数据库")) return "local";
  if (label.includes("AI")) return "ai";
  if (label.includes("必填")) return "missing";
  return "exact";
}

export function gridToExportFields(
  grid: {
    字段: string;
    值: string;
    来源: string;
    单元格: string;
    必填: string;
  }[],
) {
  return grid.map((g) => ({
    key: g.字段,
    label: g.字段,
    value: g.值,
    source: sourceLabelToKind(g.来源),
    cell: g.单元格,
    required: g.必填 === "是",
  }));
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      const base64 = result.includes(",") ? result.split(",")[1] : result;
      resolve(base64);
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
