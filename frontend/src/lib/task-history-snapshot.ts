import type { CustomsPackageData, CustomsSource } from "@/lib/api/customs";
import type {
  BoxEditorApiRow,
  BoxMetricRow,
  InvoiceDraftResponse,
  ShipmentBundle,
  TailPoolRow,
} from "@/lib/api/workflow";
import type { ActualPlacementFee } from "@/lib/api/step1";
import { DEFAULT_THROW_RATIO } from "@/constants";
import { DEFAULT_TRANSPORT_MODE, normalizeTransportMode, type TransportMode } from "@/lib/transport-mode";
import { cellMetaFromFills } from "@/lib/invoice-spreadsheet";
import {
  cloneInvoiceSessions,
  type ShipmentInvoiceSession,
} from "@/lib/invoice-session";
import { apiRowsToRows, rowsToApi, type Row } from "@/lib/step1-rows";
import { parseStaleness, type WorkflowStaleness } from "@/lib/workflow-invalidation";
import { inferHighestReached } from "@/lib/workflow-steps";

export interface CustomsSessionSnapshot {
  source: CustomsSource;
  exporterId: string;
  orderNo: string;
  selectedIds: string[];
  data: CustomsPackageData | null;
  previewSig: string;
  activeTab: string;
}

export function batchFromTaskName(name: string): string {
  const found = /第\s*(\d+)\s*批/.exec(name || "");
  return found?.[1] ?? "";
}

export interface TaskHistorySnapshot {
  task_id: string;
  task_name: string;
  /** 任务名里的「第N批」。文件名没有批次时，校验仍用这个值。 */
  batch?: string;
  step: number;
  saved_at?: string;
  input_df: ReturnType<typeof rowsToApi>;
  fnsku_overrides: Record<string, string>;
  box_editor_df: BoxEditorApiRow[];
  box_locked: boolean;
  step4_validated: boolean;
  step4_shipment_bundle: Array<{
    shipment_id: string;
    warehouse: string;
    csv_b64: string;
    pdf_b64: string;
    parsed_shipment?: Record<string, unknown>;
  }>;
  step4_status_lines: string[];
  step4_validation_errors: string[];
  step4_forwarder_df: Record<string, unknown>[];
  react_step3_matrix: Record<string, unknown>[];
  react_step3_box_count: number;
  react_step3_sku_count: number;
  react_worker_packing_preview: Record<string, unknown>[];
  react_worker_packing_warehouses: string[];
  react_shipping_sheet: Record<string, unknown>[];
  react_shipping_sheet_legend: Record<string, unknown>[];
  react_actual_placement_fee: ActualPlacementFee | null;
  react_metrics: BoxMetricRow[];
  react_tail_pool: TailPoolRow[];
  react_has_overweight: boolean;
  react_throw_ratio: number;
  react_selected_shipment_id: string;
  /** 当前选中货件的发票草稿（与 sessions 中对应项同步） */
  react_invoice_draft: InvoiceDraftResponse | null;
  react_invoice_template_base64: string | null;
  /** 各货件完整发票填写会话（含单元格、来源、计费吨） */
  react_invoice_sessions_by_shipment?: Record<string, ShipmentInvoiceSession>;
  react_invoice_forwarder_id?: string;
  react_invoice_po_by_shipment?: Record<string, string>;
  react_invoice_sync_linked_edits?: boolean;
  /** Step 5 报关：来源、订单号、勾选货件、预览数据与编辑结果 */
  react_customs_session?: CustomsSessionSnapshot | null;
  react_highest_reached_step?: number;
  react_staleness?: WorkflowStaleness;
  react_transport_mode?: TransportMode;
}

export interface WorkflowSnapshotSource {
  taskId: string;
  taskName: string;
  step: number;
  inputRows: Row[];
  fnskuOverrides: Record<string, string>;
  boxEditorApi: BoxEditorApiRow[];
  boxLocked: boolean;
  throwRatio: number;
  step3Matrix: Record<string, unknown>[];
  step3BoxCount: number;
  step3SkuCount: number;
  metrics: BoxMetricRow[];
  tailPool: TailPoolRow[];
  hasOverweight: boolean;
  step4Ok: boolean;
  step4StatusLines: string[];
  step4Errors: string[];
  workerPackingPreview: Record<string, unknown>[];
  workerPackingWarehouses: string[];
  shippingSheet: Record<string, unknown>[];
  shippingSheetLegend: Record<string, unknown>[];
  forwarder: Record<string, unknown>[];
  shipments: ShipmentBundle[];
  actualPlacementFee: ActualPlacementFee | null;
  selectedShipmentId: string;
  invoiceDraft: InvoiceDraftResponse | null;
  invoiceTemplateBase64: string | null;
  invoiceSessionsByShipment: Record<string, ShipmentInvoiceSession>;
  invoiceForwarderId: string;
  invoicePoByShipment: Record<string, string>;
  invoiceSyncLinkedEdits: boolean;
  customsSession: CustomsSessionSnapshot | null;
  highestReachedStep: number;
  staleness: WorkflowStaleness;
  transportMode: TransportMode;
}

export function newTaskId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `task-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function workflowHasData(source: WorkflowSnapshotSource): boolean {
  if (source.boxLocked || source.boxEditorApi.length > 0 || source.step4Ok) return true;
  if (source.customsSession?.data) return true;
  if (Object.values(source.invoiceSessionsByShipment).some((s) => s.sheetPhase === "filled")) {
    return true;
  }
  return source.inputRows.some((r) => r.sku.trim());
}

function normalizeInvoiceSessions(
  snapshot: Record<string, unknown>,
  selectedShipmentId: string,
  legacyDraft: InvoiceDraftResponse | null,
): Record<string, ShipmentInvoiceSession> {
  const raw = snapshot.react_invoice_sessions_by_shipment as
    | Record<string, ShipmentInvoiceSession>
    | undefined;
  if (raw && Object.keys(raw).length > 0) {
    return cloneInvoiceSessions(raw);
  }
  if (legacyDraft && selectedShipmentId) {
    const dataCells = legacyDraft.cells.filter((c) => !c.clear);
    return {
      [selectedShipmentId]: {
        draft: legacyDraft,
        cellMeta: cellMetaFromFills(dataCells),
        revenueTon: legacyDraft.revenue_ton ?? null,
        sheetPhase: "filled",
      },
    };
  }
  return {};
}

function normalizeCustomsSession(
  snapshot: Record<string, unknown>,
): CustomsSessionSnapshot | null {
  const raw = snapshot.react_customs_session as CustomsSessionSnapshot | null | undefined;
  if (!raw || typeof raw !== "object") return null;
  return {
    source: raw.source === "shipment" ? "shipment" : "invoice",
    exporterId: String(raw.exporterId ?? ""),
    orderNo: String(raw.orderNo ?? ""),
    selectedIds: Array.isArray(raw.selectedIds) ? [...raw.selectedIds] : [],
    data: raw.data ?? null,
    previewSig: String(raw.previewSig ?? ""),
    activeTab: String(raw.activeTab ?? "declaration"),
  };
}

export function buildTaskHistorySnapshot(source: WorkflowSnapshotSource): TaskHistorySnapshot {
  return {
    task_id: source.taskId,
    task_name: source.taskName,
    batch: batchFromTaskName(source.taskName),
    step: source.step,
    saved_at: new Date().toISOString(),
    input_df: rowsToApi(source.inputRows).filter((r) => String(r.SKU简称 || "").trim()),
    fnsku_overrides: { ...source.fnskuOverrides },
    box_editor_df: source.boxEditorApi.map((r) => ({ ...r })),
    box_locked: source.boxLocked,
    step4_validated: source.step4Ok,
    step4_shipment_bundle: source.shipments.map((s) => ({
      shipment_id: s.shipment_id,
      warehouse: s.warehouse,
      csv_b64: s.csv_base64,
      pdf_b64: s.pdf_base64,
      ...(s.parsed_shipment ? { parsed_shipment: s.parsed_shipment } : {}),
    })),
    step4_status_lines: [...source.step4StatusLines],
    step4_validation_errors: [...source.step4Errors],
    step4_forwarder_df: source.forwarder.map((r) => ({ ...r })),
    react_step3_matrix: source.step3Matrix.map((r) => ({ ...r })),
    react_step3_box_count: source.step3BoxCount,
    react_step3_sku_count: source.step3SkuCount,
    react_worker_packing_preview: source.workerPackingPreview.map((r) => ({ ...r })),
    react_worker_packing_warehouses: [...source.workerPackingWarehouses],
    react_shipping_sheet: source.shippingSheet.map((r) => ({ ...r })),
    react_shipping_sheet_legend: source.shippingSheetLegend.map((r) => ({ ...r })),
    react_actual_placement_fee: source.actualPlacementFee,
    react_metrics: source.metrics.map((r) => ({ ...r })),
    react_tail_pool: source.tailPool.map((r) => ({ ...r })),
    react_has_overweight: source.hasOverweight,
    react_throw_ratio: source.throwRatio,
    react_selected_shipment_id: source.selectedShipmentId,
    react_invoice_draft: source.invoiceDraft,
    react_invoice_template_base64: source.invoiceTemplateBase64,
    react_invoice_sessions_by_shipment: cloneInvoiceSessions(source.invoiceSessionsByShipment),
    react_invoice_forwarder_id: source.invoiceForwarderId,
    react_invoice_po_by_shipment: { ...source.invoicePoByShipment },
    react_invoice_sync_linked_edits: source.invoiceSyncLinkedEdits,
    react_customs_session: source.customsSession
      ? {
          ...source.customsSession,
          selectedIds: [...source.customsSession.selectedIds],
          data: source.customsSession.data
            ? (JSON.parse(JSON.stringify(source.customsSession.data)) as CustomsPackageData)
            : null,
        }
      : null,
    react_highest_reached_step: source.highestReachedStep,
    react_staleness: { ...source.staleness },
    react_transport_mode: normalizeTransportMode(source.transportMode),
  };
}

export interface AppliedTaskHistory {
  taskId: string;
  taskName: string;
  step: number;
  inputRows: Row[];
  fnskuOverrides: Record<string, string>;
  boxEditorApi: BoxEditorApiRow[];
  boxLocked: boolean;
  throwRatio: number;
  step3Matrix: Record<string, unknown>[];
  step3BoxCount: number;
  step3SkuCount: number;
  metrics: BoxMetricRow[];
  tailPool: TailPoolRow[];
  hasOverweight: boolean;
  step4Ok: boolean;
  step4StatusLines: string[];
  step4Errors: string[];
  workerPackingPreview: Record<string, unknown>[];
  workerPackingWarehouses: string[];
  shippingSheet: Record<string, unknown>[];
  shippingSheetLegend: Record<string, unknown>[];
  forwarder: Record<string, unknown>[];
  shipments: ShipmentBundle[];
  actualPlacementFee: ActualPlacementFee | null;
  selectedShipmentId: string;
  invoiceDraft: InvoiceDraftResponse | null;
  invoiceTemplateBase64: string | null;
  invoiceSessionsByShipment: Record<string, ShipmentInvoiceSession>;
  invoiceForwarderId: string;
  invoicePoByShipment: Record<string, string>;
  invoiceSyncLinkedEdits: boolean;
  customsSession: CustomsSessionSnapshot | null;
  highestReachedStep: number;
  staleness: WorkflowStaleness;
  transportMode: TransportMode;
}

export function applyTaskHistorySnapshot(snapshot: Record<string, unknown>): AppliedTaskHistory {
  const inputRows = apiRowsToRows((snapshot.input_df as TaskHistorySnapshot["input_df"]) ?? []);
  const bundle = (snapshot.step4_shipment_bundle as TaskHistorySnapshot["step4_shipment_bundle"]) ?? [];
  const shipments: ShipmentBundle[] = bundle
    .filter((item) => item.csv_b64 && item.pdf_b64)
    .map((item) => ({
      shipment_id: item.shipment_id,
      warehouse: item.warehouse,
      csv_base64: item.csv_b64,
      pdf_base64: item.pdf_b64,
      ...(item.parsed_shipment ? { parsed_shipment: item.parsed_shipment } : {}),
    }));

  const selectedShipmentId = String(
    snapshot.react_selected_shipment_id ?? shipments[0]?.shipment_id ?? "",
  );
  const legacyDraft = (snapshot.react_invoice_draft as InvoiceDraftResponse | null) ?? null;
  const invoiceSessionsByShipment = normalizeInvoiceSessions(
    snapshot,
    selectedShipmentId,
    legacyDraft,
  );
  const sessionDraft = selectedShipmentId
    ? invoiceSessionsByShipment[selectedShipmentId]?.draft
    : null;
  const invoiceDraft = sessionDraft ?? legacyDraft;
  const customsSession = normalizeCustomsSession(snapshot);
  const step4Ok = Boolean(snapshot.step4_validated ?? snapshot.react_step4_ok);
  const boxLocked = Boolean(snapshot.box_locked);
  const step = Number(snapshot.step || 1);
  const staleness = parseStaleness(snapshot.react_staleness);
  const highestReachedStep = inferHighestReached({
    step,
    highestReachedStep: Number(snapshot.react_highest_reached_step ?? 0) || undefined,
    boxLocked,
    step4Ok,
    hasInvoice: Object.keys(invoiceSessionsByShipment).length > 0,
    hasCustoms: Boolean(customsSession?.data),
  });

  return {
    taskId: String(snapshot.task_id || newTaskId()),
    taskName: String(snapshot.task_name || ""),
    step,
    inputRows,
    fnskuOverrides: { ...(snapshot.fnsku_overrides as Record<string, string>) },
    boxEditorApi: [...((snapshot.box_editor_df as BoxEditorApiRow[]) ?? [])],
    boxLocked,
    throwRatio: Number(snapshot.react_throw_ratio ?? snapshot.step4_throw_ratio ?? DEFAULT_THROW_RATIO),
    step3Matrix: [...((snapshot.react_step3_matrix as Record<string, unknown>[]) ?? [])],
    step3BoxCount: Number(snapshot.react_step3_box_count ?? 0),
    step3SkuCount: Number(snapshot.react_step3_sku_count ?? 0),
    metrics: [...((snapshot.react_metrics as BoxMetricRow[]) ?? [])],
    tailPool: [...((snapshot.react_tail_pool as TailPoolRow[]) ?? [])],
    hasOverweight: Boolean(snapshot.react_has_overweight),
    step4Ok,
    step4StatusLines: [...((snapshot.step4_status_lines as string[]) ?? [])],
    step4Errors: [...((snapshot.step4_validation_errors as string[]) ?? [])],
    workerPackingPreview: [
      ...((snapshot.react_worker_packing_preview as Record<string, unknown>[]) ?? []),
    ],
    workerPackingWarehouses: [
      ...((snapshot.react_worker_packing_warehouses as string[]) ?? []),
    ],
    shippingSheet: [...((snapshot.react_shipping_sheet as Record<string, unknown>[]) ?? [])],
    shippingSheetLegend: [
      ...((snapshot.react_shipping_sheet_legend as Record<string, unknown>[]) ?? []),
    ],
    forwarder: [...((snapshot.step4_forwarder_df as Record<string, unknown>[]) ?? [])],
    shipments,
    actualPlacementFee:
      (snapshot.react_actual_placement_fee as ActualPlacementFee | null) ?? null,
    selectedShipmentId,
    invoiceDraft,
    invoiceTemplateBase64:
      (snapshot.react_invoice_template_base64 as string | null) ??
      (snapshot.invoice_template_bytes as string | null) ??
      null,
    invoiceSessionsByShipment,
    invoiceForwarderId: String(snapshot.react_invoice_forwarder_id ?? ""),
    invoicePoByShipment: {
      ...((snapshot.react_invoice_po_by_shipment as Record<string, string>) ?? {}),
    },
    invoiceSyncLinkedEdits: snapshot.react_invoice_sync_linked_edits !== false,
    customsSession,
    highestReachedStep,
    staleness,
    transportMode: normalizeTransportMode(snapshot.react_transport_mode ?? DEFAULT_TRANSPORT_MODE),
  };
}
