import type {
  ApiSkuRow,
  BoxEditorApiRow,
  BoxMetricRow,
  CalculateBoxesResponse,
  BoxMetricsResponse,
  FbaCompliance,
  InvoiceDraftResponse,
  InvoicePreviewResponse,
  PackingMode,
  ShipmentValidateResponse,
  Step3PreviewResponse,
  TailPoolRow,
  WorkflowPayload,
} from "@/types";
import { apiFetchJson, apiPostJson, apiUpload, ApiError, downloadPostBlob, downloadUploadBlob, resolveApiUrl } from "@/lib/api/client";

export type * from "@/types/boxing";
export type * from "@/types/shipment";
export type * from "@/types/invoice";

function payload(body: WorkflowPayload) {
  return {
    rows: body.rows,
    box_editor: body.box_editor,
    fnsku_overrides: body.fnsku_overrides ?? {},
    transport_mode: body.transport_mode ?? "spd_partnered",
    confirm_weight_warnings: Boolean(body.confirm_weight_warnings),
  };
}

export function calculateBoxes(
  rows: ApiSkuRow[],
  fnskuOverrides?: Record<string, string>,
  transportMode?: string,
) {
  return apiPostJson<CalculateBoxesResponse>("/api/calculate_boxes", {
    rows,
    fnsku_overrides: fnskuOverrides ?? {},
    transport_mode: transportMode ?? "spd_partnered",
  });
}

export function fetchBoxMetrics(body: WorkflowPayload) {
  return apiPostJson<BoxMetricsResponse>("/api/box_metrics", payload(body));
}

export function fetchTailPool(body: WorkflowPayload) {
  return apiPostJson<{ tail_pool: TailPoolRow[] }>("/api/tail_pool", payload(body));
}

export function assignTail(body: WorkflowPayload & { sku: string; qty: number; box_no: number }) {
  return apiPostJson<{
    box_editor: BoxEditorApiRow[];
    metrics: BoxMetricRow[];
    has_overweight: boolean;
    fba_compliance: FbaCompliance;
    has_fba_block: boolean;
  }>("/api/box/assign_tail", {
    ...payload(body),
    sku: body.sku,
    qty: body.qty,
    box_no: body.box_no,
  });
}

export function fetchStep3Preview(body: WorkflowPayload) {
  return apiPostJson<Step3PreviewResponse>("/api/export/step3/preview", payload(body));
}

export function downloadInternalExport(body: WorkflowPayload) {
  return downloadPostBlob("/api/export/step3/internal", payload(body), "内部留档表.xlsx");
}

export function downloadAmazonExport(body: WorkflowPayload) {
  return downloadPostBlob("/api/export/step3/amazon", payload(body), "Send to Amazon表格.xlsx");
}

export function downloadStep3Bundle(body: WorkflowPayload) {
  return downloadPostBlob("/api/export/step3/bundle", payload(body), "Step3导出.zip");
}

export function fetchStaPrecheck(body: WorkflowPayload) {
  return apiPostJson<{ highlights: { row: number; column: string; message: string }[] }>(
    "/api/export/step3/sta_precheck",
    payload(body),
  );
}

export interface ValidateWorkflowContext {
  taskId?: string;
  taskName?: string;
  batch?: string;
}

function batchFromLabel(text: string): string {
  const found = /第\s*(\d+)\s*批/.exec(text || "");
  return found?.[1] ?? "";
}

function sourcePath(file: File): string {
  const relative = file.webkitRelativePath || "";
  return relative || file.name;
}

export function validateShipments(
  csvFiles: File[],
  pdfFiles: File[],
  throwRatio?: number,
  boxEditor?: BoxEditorApiRow[],
  inputRows?: ApiSkuRow[],
  packingMode: PackingMode = "amazon_led",
  context?: ValidateWorkflowContext,
) {
  const form = buildValidateFormData(
    csvFiles,
    pdfFiles,
    throwRatio,
    boxEditor,
    inputRows,
    packingMode,
    context,
  );
  return apiUpload<ShipmentValidateResponse>("/api/shipments/validate", form);
}

function buildValidateFormData(
  csvFiles: File[],
  pdfFiles: File[],
  throwRatio?: number,
  boxEditor?: BoxEditorApiRow[],
  inputRows?: ApiSkuRow[],
  packingMode: PackingMode = "amazon_led",
  context?: ValidateWorkflowContext,
) {
  const form = new FormData();
  for (const f of csvFiles) form.append("csv_files", f);
  for (const f of pdfFiles) form.append("pdf_files", f);
  if (throwRatio != null) form.append("throw_ratio", String(throwRatio));
  const paths = [...csvFiles, ...pdfFiles].map(sourcePath);
  const taskName = context?.taskName ?? "";
  const batch = context?.batch || batchFromLabel(taskName) || batchFromLabel(paths.join(" "));
  form.append(
    "workflow_json",
    JSON.stringify({
      box_editor: boxEditor ?? [],
      rows: inputRows ?? [],
      packing_mode: packingMode,
      task_id: context?.taskId ?? "",
      task_name: taskName,
      ...(batch ? { batch } : {}),
      source_paths: paths,
    }),
  );
  if (batch) form.append("batch", batch);
  return form;
}

/** 流式校验：实时推送当前步骤与进度（NDJSON）。 */
export function validateShipmentsWithProgress(
  csvFiles: File[],
  pdfFiles: File[],
  throwRatio: number | undefined,
  boxEditor: BoxEditorApiRow[] | undefined,
  inputRows: ApiSkuRow[] | undefined,
  packingMode: PackingMode,
  onProgress: (percent: number, message: string) => void,
  context?: ValidateWorkflowContext,
): Promise<ShipmentValidateResponse> {
  const form = buildValidateFormData(
    csvFiles,
    pdfFiles,
    throwRatio,
    boxEditor,
    inputRows,
    packingMode,
    context,
  );

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", resolveApiUrl("/api/shipments/validate/stream"));
    xhr.responseType = "text";
    xhr.setRequestHeader("Accept", "application/x-ndjson");

    let offset = 0;
    let lineBuffer = "";
    let settled = false;

    const finish = (res: ShipmentValidateResponse) => {
      if (settled) return;
      settled = true;
      resolve(res);
    };

    const fail = (err: ApiError) => {
      if (settled) return;
      settled = true;
      reject(err);
    };

    const drainNdjson = () => {
      const chunk = xhr.responseText.slice(offset);
      if (!chunk) return;
      offset = xhr.responseText.length;
      lineBuffer += chunk;
      const lines = lineBuffer.split("\n");
      lineBuffer = lines.pop() ?? "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        try {
          const ev = JSON.parse(trimmed) as {
            event?: string;
            message?: string;
            percent?: number;
            data?: ShipmentValidateResponse;
          };
          if (ev.event === "progress" && ev.message != null) {
            onProgress(ev.percent ?? 0, ev.message);
          }
          if (ev.event === "result" && ev.data) {
            finish(ev.data);
          }
        } catch {
          // 等待更多字节
        }
      }
    };

    xhr.upload.onloadstart = () => onProgress(1, "准备上传 CSV / PDF…");
    xhr.upload.onprogress = (ev) => {
      if (!ev.lengthComputable) {
        onProgress(3, `正在上传 ${csvFiles.length} 个 CSV、${pdfFiles.length} 个 PDF…`);
        return;
      }
      const pct = Math.min(8, Math.round((ev.loaded / ev.total) * 8));
      onProgress(pct, `正在上传文件… ${Math.round((ev.loaded / ev.total) * 100)}%`);
    };

    xhr.onprogress = () => drainNdjson();

    xhr.onload = () => {
      drainNdjson();
      if (lineBuffer.trim()) {
        try {
          const ev = JSON.parse(lineBuffer.trim()) as {
            event?: string;
            data?: ShipmentValidateResponse;
          };
          if (ev.event === "result" && ev.data) {
            finish(ev.data);
            return;
          }
        } catch {
          // fall through
        }
      }
      if (!settled) {
        if (xhr.status >= 200 && xhr.status < 300) {
          fail(new ApiError(xhr.status, "校验流结束但未收到结果"));
        } else {
          let message = `HTTP ${xhr.status}`;
          try {
            const body = JSON.parse(xhr.responseText || "{}");
            if (typeof body?.detail === "string") message = body.detail;
          } catch {
            // ignore
          }
          fail(new ApiError(xhr.status, message));
        }
      }
    };

    xhr.onerror = () => fail(new ApiError(0, "网络错误，请确认后端已启动"));
    xhr.send(form);
  });
}

export function downloadWorkerPackingList(
  preview: Record<string, unknown>[],
  warehouses?: string[],
) {
  return downloadPostBlob(
    "/api/export/worker_packing_preview",
    {
      worker_packing_preview: preview,
      worker_packing_warehouses: warehouses ?? [],
    },
    "工人装箱贴标实操单.xlsx",
  );
}

/** @deprecated 重传 CSV/PDF 较慢，请用 downloadWorkerPackingList(preview) */
export function downloadWorkerPackingListWithUpload(
  csvFiles: File[],
  pdfFiles: File[],
  boxEditor: BoxEditorApiRow[],
  inputRows: ApiSkuRow[],
  packingMode: PackingMode = "amazon_led",
) {
  const form = new FormData();
  for (const f of csvFiles) form.append("csv_files", f);
  for (const f of pdfFiles) form.append("pdf_files", f);
  form.append(
    "workflow_json",
    JSON.stringify({
      box_editor: boxEditor,
      rows: inputRows,
      packing_mode: packingMode,
    }),
  );
  return downloadUploadBlob("/api/export/worker_packing_list", form, "工人装箱贴标实操单.xlsx");
}

export function downloadShippingSheetExport(
  shippingSheet: Record<string, unknown>[],
  shippingSheetLegend?: Record<string, unknown>[],
  step1Rows?: ApiSkuRow[],
) {
  return downloadPostBlob(
    "/api/export/shipping_sheet",
    {
      shipping_sheet: shippingSheet,
      shipping_sheet_legend: shippingSheetLegend ?? [],
      step1_rows: step1Rows,
    },
    "发货表.xlsx",
  );
}

export function downloadForwarderExport(forwarder: Record<string, unknown>[]) {
  return downloadPostBlob("/api/export/forwarder", { forwarder }, "货代表.xlsx");
}

export function previewInvoice(template_base64: string) {
  return apiPostJson<InvoicePreviewResponse>("/api/invoice/preview", { template_base64 });
}

export function fillInvoice(body: {
  shipment_id: string;
  csv_base64?: string;
  pdf_base64?: string;
  parsed_shipment?: Record<string, unknown>;
  template_base64?: string;
  forwarder_id?: string;
  po_number?: string;
  warehouse?: string;
  workflow_json?: Record<string, unknown>;
  api_key?: string;
  model?: string;
  temperature?: number;
}) {
  return apiPostJson<InvoiceDraftResponse>("/api/invoice/generate", body);
}

export function generateInvoice(body: {
  shipment_id: string;
  csv_base64: string;
  pdf_base64: string;
  template_base64?: string;
  api_key?: string;
  model?: string;
  temperature?: number;
}) {
  return apiPostJson<InvoiceDraftResponse>("/api/invoice/generate", body);
}

export function exportInvoice(body: {
  template_base64?: string;
  template_hash?: string;
  forwarder_id?: string;
  shipment_id: string;
  warehouse_code: string;
  template_sheet: string;
  fields: Record<string, unknown>[];
  snapshot?: unknown;
}) {
  return downloadPostBlob("/api/export_invoice", body, `货代发票_${body.shipment_id}.xlsx`);
}

export function fetchConfigLimits() {
  return apiFetchJson<{ weight_limit_kg: number; throw_ratio: number }>("/api/config/limits");
}
