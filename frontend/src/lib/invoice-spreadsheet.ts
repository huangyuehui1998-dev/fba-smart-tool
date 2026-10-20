import { api, type Cell, type Sheet } from "@fortune-sheet/core";
import { sourceLabelToKind } from "@/lib/box-editor";

export type CellSourceKind = "exact" | "local" | "ai" | "missing" | "preview";

export interface InvoiceCellFill {
  cell: string;
  value: string;
  source: string;
  field_key?: string;
  required?: boolean;
  /** 清空区单元格：只擦除内容，不覆盖背景色 */
  clear?: boolean;
}

export interface CellMeta {
  source: CellSourceKind;
  fieldKey?: string;
  required?: boolean;
}

/** FortuneSheet `bg` 属性使用的十六进制色值 */
export const SOURCE_BG_HEX: Record<CellSourceKind, string> = {
  preview: "#ffffff",
  exact: "#d1fae5",
  local: "#e0f2fe",
  ai: "#fef3c7",
  missing: "#ffe4e6",
};

export const CELL_SOURCE_STYLES: Record<
  CellSourceKind,
  { bg: string; label: string }
> = {
  preview: { bg: "bg-background", label: "模板" },
  exact: { bg: "bg-emerald-50", label: "精准提取" },
  local: { bg: "bg-sky-50", label: "主数据库" },
  ai: { bg: "bg-amber-50", label: "AI 推理" },
  missing: { bg: "bg-rose-50", label: "必填待补" },
};

export function colIndexToLetter(col: number): string {
  let n = col + 1;
  let s = "";
  while (n > 0) {
    n -= 1;
    s = String.fromCharCode(65 + (n % 26)) + s;
    n = Math.floor(n / 26);
  }
  return s;
}

export function parseCellRef(ref: string): { row: number; col: number } {
  const m = /^([A-Z]+)(\d+)$/i.exec(ref.trim());
  if (!m) {
    throw new Error(`Invalid cell reference: ${ref}`);
  }
  const letters = m[1].toUpperCase();
  let col = 0;
  for (let i = 0; i < letters.length; i += 1) {
    col = col * 26 + (letters.charCodeAt(i) - 64);
  }
  col -= 1;
  return { row: parseInt(m[2], 10) - 1, col };
}

export function formatCellRef(row: number, col: number): string {
  return `${colIndexToLetter(col)}${row + 1}`;
}

export function cellMetaFromFills(fills: InvoiceCellFill[]): Record<string, CellMeta> {
  const meta: Record<string, CellMeta> = {};
  for (const fill of fills) {
    if (!fill.cell) continue;
    meta[fill.cell.toUpperCase()] = {
      source: sourceLabelToKind(fill.source),
      fieldKey: fill.field_key,
      required: fill.required ?? fill.source.includes("必填"),
    };
  }
  return meta;
}

export function buildExportFieldsFromCellMeta(
  cellMeta: Record<string, CellMeta>,
  getValue: (cell: string) => string,
): Array<{
  key: string;
  label: string;
  value: string;
  cell: string;
  required: boolean;
  source: string;
}> {
  return Object.entries(cellMeta)
    .map(([cell, meta]) => {
      const key = meta.fieldKey ?? cell;
      const value = getValue(cell).trim();
      return {
        key,
        label: key,
        value,
        cell: cell.toUpperCase(),
        required: meta.required ?? false,
        source: meta.source === "missing" ? "red" : "green",
      };
    })
    .filter((row) => row.value.length > 0);
}

export function buildExportFieldsForInvoiceExport(
  draftCells: InvoiceCellFill[] | undefined,
  cellMeta: Record<string, CellMeta>,
  getValue: (cell: string) => string,
): Array<{
  key: string;
  label: string;
  value: string;
  cell: string;
  required: boolean;
  source: string;
}> {
  const rows: ReturnType<typeof buildExportFieldsFromCellMeta> = [];
  const seen = new Set<string>();

  const push = (cell: string, meta: CellMeta | undefined, fallbackValue?: string) => {
    const upper = cell.toUpperCase();
    if (seen.has(upper)) return;
    const value = (getValue(upper) || fallbackValue || "").trim();
    if (!value) return;
    seen.add(upper);
    const key = meta?.fieldKey ?? upper;
    rows.push({
      key,
      label: key,
      value,
      cell: upper,
      required: meta?.required ?? false,
      source: meta?.source === "missing" ? "red" : "green",
    });
  };

  for (const fill of draftCells ?? []) {
    if (!fill.cell) continue;
    push(fill.cell, cellMeta[fill.cell.toUpperCase()], fill.value);
  }
  for (const [cell, meta] of Object.entries(cellMeta)) {
    push(cell, meta);
  }
  return rows;
}

export function missingRequiredFromCellMeta(
  cellMeta: Record<string, CellMeta>,
  getValue: (cell: string) => string,
): string[] {
  const FIELD_LABELS: Record<string, string> = {
    reference_id: "Reference ID / ID号",
    sku_image: "SKU图片",
  };
  const requiredKeys = new Map<string, boolean>();
  for (const [cell, meta] of Object.entries(cellMeta)) {
    if (!meta.required) continue;
    const key = meta.fieldKey ?? cell;
    const val = getValue(cell).trim();
    if (val) {
      requiredKeys.set(key, true);
    } else if (!requiredKeys.has(key)) {
      requiredKeys.set(key, false);
    }
  }
  return [...requiredKeys.entries()]
    .filter(([, ok]) => !ok)
    .map(([key]) => FIELD_LABELS[key] ?? key);
}

export function cloneSheets<T>(sheets: T[]): T[] {
  return JSON.parse(JSON.stringify(sheets)) as T[];
}

function sheetToDataMatrix(sheet: Sheet): (Cell | null)[][] {
  const rowCount = Math.max(Number(sheet.row) || 0, 36);
  const colCount = Math.max(Number(sheet.column) || 0, 18);
  if (sheet.data?.length) {
    return sheet.data as (Cell | null)[][];
  }
  if (sheet.celldata?.length) {
    return api.celldataToData(sheet.celldata, rowCount, colCount) ?? [];
  }
  return Array.from({ length: rowCount }, () => Array(colCount).fill(null));
}

function writeCell(
  matrix: (Cell | null)[][],
  row: number,
  col: number,
  patch: Partial<Cell>,
): void {
  while (matrix.length <= row) {
    matrix.push([]);
  }
  const rowArr = matrix[row]!;
  while (rowArr.length <= col) {
    rowArr.push(null);
  }
  const prev = rowArr[col];
  rowArr[col] = prev ? { ...prev, ...patch } : (patch as Cell);
}

/** 将填充结果合并进模板快照，供 Workbook 重挂载或剪贴板导出使用。 */
export function applyFillsToSheets(sheets: Sheet[], fills: InvoiceCellFill[]): Sheet[] {
  const cloned = cloneSheets(sheets);
  if (!cloned.length) return cloned;

  const meta = cellMetaFromFills(fills);

  return cloned.map((sheet, index) => {
    if (index !== 0) return sheet;

    const data = sheetToDataMatrix(sheet);

    for (const fill of fills) {
      if (!fill.cell) continue;
      try {
        const { row, col } = parseCellRef(fill.cell);
        const source = meta[fill.cell.toUpperCase()]?.source ?? "preview";
        if (fill.value === "" || fill.value == null) {
          writeCell(data, row, col, { v: "", m: "" });
        } else {
          const patch: Partial<Cell> = {
            v: fill.value,
            m: String(fill.value),
          };
          if (!fill.clear) {
            patch.bg = SOURCE_BG_HEX[source];
          }
          writeCell(data, row, col, patch);
        }
      } catch {
        // skip invalid refs
      }
    }

    const rowCount = Math.max(Number(sheet.row) || 0, data.length, 36);
    const colCount = Math.max(Number(sheet.column) || 0, data[0]?.length ?? 0, 18);
    while (data.length < rowCount) {
      data.push(Array(colCount).fill(null));
    }
    for (const row of data) {
      while (row.length < colCount) {
        row.push(null);
      }
    }

    const { data: _data, celldata: _celldata, calcChain: _calcChain, ...rest } = sheet;
    return {
      ...rest,
      row: rowCount,
      column: colCount,
      data,
      celldata: api.dataToCelldata(data),
      calcChain: [],
    };
  });
}

type FortuneMerge = { r: number; c: number; rs: number; cs: number };

function mergeOwner(
  merges: FortuneMerge[],
  row: number,
  col: number,
): { row: number; col: number; rowspan: number; colspan: number } | null {
  for (const m of merges) {
    if (row >= m.r && row < m.r + m.rs && col >= m.c && col < m.c + m.cs) {
      if (row === m.r && col === m.c) {
        return { row: m.r, col: m.c, rowspan: m.rs, colspan: m.cs };
      }
      return null;
    }
  }
  return { row, col, rowspan: 1, colspan: 1 };
}

/** 生成可粘贴到 Excel 的 HTML 表格（含边框、合并、列宽）。 */
export function buildClipboardHtmlTable(
  getValue: (row: number, col: number) => string,
  options: {
    rowCount: number;
    colCount: number;
    merges?: FortuneMerge[];
    columnWidths?: Record<string, number>;
  },
): string {
  const { rowCount, colCount, merges = [], columnWidths = {} } = options;
  const skip = new Set<string>();

  for (const m of merges) {
    for (let r = m.r; r < m.r + m.rs; r += 1) {
      for (let c = m.c; c < m.c + m.cs; c += 1) {
        if (r === m.r && c === m.c) continue;
        skip.add(`${r},${c}`);
      }
    }
  }

  const rows: string[] = [];
  for (let r = 0; r < rowCount; r += 1) {
    const cells: string[] = [];
    for (let c = 0; c < colCount; c += 1) {
      if (skip.has(`${r},${c}`)) continue;
      const owner = mergeOwner(merges, r, c);
      if (!owner) continue;
      const val = getValue(r, c).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      const width = columnWidths[String(c)];
      const widthStyle = width ? `width:${Math.round(width)}px;` : "";
      const span =
        owner.rowspan > 1 || owner.colspan > 1
          ? ` rowspan="${owner.rowspan}" colspan="${owner.colspan}"`
          : "";
      cells.push(
        `<td${span} style="border:1px solid #000;padding:2px 4px;${widthStyle}font-family:'Microsoft YaHei','SimSun',Arial,sans-serif;font-size:10pt;mso-number-format:'\\@';">${val}</td>`,
      );
    }
    rows.push(`<tr>${cells.join("")}</tr>`);
  }

  return (
    `<html><head><meta charset="utf-8"></head><body>` +
    `<table cellspacing="0" cellpadding="0" style="border-collapse:collapse;font-family:'Microsoft YaHei','SimSun',Arial,sans-serif;">` +
    rows.join("") +
    `</table></body></html>`
  );
}
