import type { InvoiceDraftResponse } from "@/lib/api/workflow";
import type { CellMeta, InvoiceCellFill } from "@/lib/invoice-spreadsheet";
import { parseCellRef } from "@/lib/invoice-spreadsheet";

export type SheetPhase = "idle" | "preview" | "filled";

export interface ShipmentInvoiceSession {
  draft: InvoiceDraftResponse | null;
  cellMeta: Record<string, CellMeta>;
  revenueTon: number | null;
  sheetPhase: SheetPhase;
}

const HEADER_SYNC_FIELDS = new Set([
  "po_number",
  "reference_id",
  "revenue_ton",
  "shipping_mark",
  "fba_id",
  "shipment_id",
]);

export function emptyInvoiceSession(): ShipmentInvoiceSession {
  return { draft: null, cellMeta: {}, revenueTon: null, sheetPhase: "idle" };
}

function excelRow(cell: string): number {
  try {
    return parseCellRef(cell).row + 1;
  } catch {
    return -1;
  }
}

export function skuForCellRow(cells: InvoiceCellFill[], cell: string): string {
  const row = excelRow(cell);
  if (row < 0) return "";
  for (const c of cells) {
    if (c.field_key === "sku" && excelRow(c.cell) === row) {
      return String(c.value ?? "").trim();
    }
  }
  return "";
}

export function shouldSyncField(fieldKey: string, sku: string): boolean {
  if (HEADER_SYNC_FIELDS.has(fieldKey)) return true;
  return Boolean(sku);
}

export function syncDraftCellValue(
  draft: InvoiceDraftResponse,
  editedCell: string,
  value: string,
  fieldKey: string,
  rowSku: string,
): InvoiceDraftResponse {
  const editedRow = excelRow(editedCell);
  const cells = draft.cells.map((c) => {
    if (!c.field_key || c.field_key !== fieldKey) return c;
    if (HEADER_SYNC_FIELDS.has(fieldKey)) {
      return { ...c, value };
    }
    if (rowSku && skuForCellRow(draft.cells, c.cell) === rowSku) {
      return { ...c, value };
    }
    if (!rowSku && excelRow(c.cell) === editedRow) {
      return { ...c, value };
    }
    return c;
  });
  return { ...draft, cells };
}

export function mergeSessions(
  prev: Record<string, ShipmentInvoiceSession>,
  shipmentId: string,
  patch: Partial<ShipmentInvoiceSession>,
): Record<string, ShipmentInvoiceSession> {
  const base = prev[shipmentId] ?? emptyInvoiceSession();
  return { ...prev, [shipmentId]: { ...base, ...patch } };
}

/** 将表格中当前单元格值写回 draft，便于 fbox 完整存档。 */
export function draftWithLiveSpreadsheetCells(
  draft: InvoiceDraftResponse,
  cellMeta: Record<string, CellMeta>,
  getValue: (cell: string) => string,
): InvoiceDraftResponse {
  const touched = new Set<string>();
  const cells = draft.cells.map((c) => {
    if (!c.cell) return c;
    const ref = c.cell.toUpperCase();
    touched.add(ref);
    const live = getValue(ref).trim();
    return live ? { ...c, value: live } : c;
  });
  for (const cell of Object.keys(cellMeta)) {
    const ref = cell.toUpperCase();
    if (touched.has(ref)) continue;
    const live = getValue(ref).trim();
    if (!live) continue;
    cells.push({
      cell: ref,
      value: live,
      source: cellMeta[ref]?.source === "missing" ? "red" : "green",
      field_key: cellMeta[ref]?.fieldKey,
      required: cellMeta[ref]?.required,
    });
  }
  return { ...draft, cells };
}

export function cloneInvoiceSessions(
  sessions: Record<string, ShipmentInvoiceSession>,
): Record<string, ShipmentInvoiceSession> {
  return JSON.parse(JSON.stringify(sessions)) as Record<string, ShipmentInvoiceSession>;
}
