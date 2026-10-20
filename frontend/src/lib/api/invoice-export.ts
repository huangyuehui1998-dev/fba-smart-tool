import { ApiError, resolveApiUrl } from "@/lib/api/client";

export type ExportForwarder = { id: string; name: string; adapter: string };
export type ExportIssue = { code: string; message: string; [k: string]: unknown };
export type ExportPreview = {
  file_name: string;
  shipment_id: string;
  warehouse: string;
  warehouse_source?: string;
  warnings: ExportIssue[];
  box_count: number;
  total_qty: number;
  total_value: number;
  ranges: { box: string; fnsku: string; qty: number; weight: number; mixed: boolean }[];
  lines: { fnsku: string; qty: number; price: number; price_source: string; total: number }[];
};
export type ExportForm = {
  forwarder_id: string;
  csv: File;
  reference_id?: string;
  order_no?: string;
  warehouse?: string;
  measured?: File | null;
  /** 外箱号更正：{ 多出的 FBA 箱号: 正确的箱序号 } */
  box_id_fix?: Record<string, number>;
  /** S8-fix1：重量口径（德速 T3 / 琪珞 T6）："" = 自动（按货代原件核对），per_box = 单箱重，per_unit = 单件重 */
  weight_basis?: "" | "per_box" | "per_unit";
  /** 货代给的这票发票原件：程序按货件 CSV 核对判定重量口径 */
  weight_ref?: File | null;
};

/** 仓库定不下来（422）：候选仓库给面板下拉框用 */
export class WarehouseUndecidedError extends Error {
  candidates: string[];
  constructor(message: string, candidates: string[]) {
    super(message);
    this.candidates = candidates;
  }
}

/** 导出被拦截（409）：blocking 里逐条写了原因 */
export class ExportBlockedError extends Error {
  blocking: ExportIssue[];
  constructor(message: string, blocking: ExportIssue[]) {
    super(message);
    this.blocking = blocking;
  }
}

function formData(f: ExportForm): FormData {
  const fd = new FormData();
  fd.append("forwarder_id", f.forwarder_id);
  fd.append("csv_file", f.csv);
  if (f.reference_id) fd.append("reference_id", f.reference_id);
  if (f.order_no) fd.append("order_no", f.order_no);
  if (f.warehouse) fd.append("warehouse", f.warehouse);
  if (f.measured) fd.append("measured_file", f.measured);
  if (f.box_id_fix && Object.keys(f.box_id_fix).length) fd.append("box_id_fix", JSON.stringify(f.box_id_fix));
  if (f.weight_basis) fd.append("weight_basis", f.weight_basis);
  if (f.weight_ref) fd.append("weight_ref_file", f.weight_ref);
  return fd;
}

async function fail(res: Response): Promise<never> {
  let body: { detail?: unknown; blocking?: ExportIssue[]; warehouse_candidates?: string[] } = {};
  try {
    body = await res.json();
  } catch {
    // ignore
  }
  const msg = typeof body.detail === "string" ? body.detail : res.statusText || `HTTP ${res.status}`;
  if (res.status === 422 && Array.isArray(body.warehouse_candidates))
    throw new WarehouseUndecidedError(msg, body.warehouse_candidates);
  if (res.status === 409) throw new ExportBlockedError(msg, body.blocking || []);
  throw new ApiError(res.status, msg);
}

export async function fetchExportForwarders(): Promise<ExportForwarder[]> {
  const res = await fetch(resolveApiUrl("/api/invoice-export/forwarders"));
  if (!res.ok) await fail(res);
  return ((await res.json()) as { forwarders: ExportForwarder[] }).forwarders;
}

export async function previewForwarderInvoice(f: ExportForm): Promise<ExportPreview> {
  const res = await fetch(resolveApiUrl("/api/invoice-export/preview"), { method: "POST", body: formData(f) });
  if (!res.ok) await fail(res);
  return (await res.json()) as ExportPreview;
}

export async function downloadForwarderInvoice(f: ExportForm): Promise<{ blob: Blob; fileName: string }> {
  const res = await fetch(resolveApiUrl("/api/invoice-export/export"), { method: "POST", body: formData(f) });
  if (!res.ok) await fail(res);
  const cd = res.headers.get("content-disposition") || "";
  const m = /filename\*=UTF-8''([^;]+)/i.exec(cd);
  return { blob: await res.blob(), fileName: m ? decodeURIComponent(m[1]) : "invoice.xlsx" };
}
