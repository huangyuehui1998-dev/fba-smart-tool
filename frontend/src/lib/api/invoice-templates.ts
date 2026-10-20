import { ApiError, resolveApiUrl } from "@/lib/api/client";

/** S8 D3：T1–T8 发票模板识别 / 解析（只读，不写库） */
export type InvoiceTemplateInfo = { id: string; name: string; forwarder?: string };
export type TemplateCandidate = { template_id: string; name: string; score: number };
export type DetectResult = {
  template_id: string | null;
  ambiguous: boolean;
  candidates: TemplateCandidate[];
  tied: string[];
  message: string;
};
export type ParseIssue = { code: string; message: string };
export type ParseProposal = { id: string; group: string; field: string; current: unknown; proposed: unknown; message: string };
export type ParsedLine = {
  sku: string;
  english_name: string;
  chinese_name: string;
  hs_code: string;
  qty: number | null;
  unit_price: number | null;
  box_range: string;
};
export type ParsedTicket = {
  template_id: string;
  forwarder: string;
  shipment_id: string;
  warehouse: string;
  box_count: number | null;
  verify_status: string;
  issues: ParseIssue[];
  proposals: ParseProposal[];
  lines: ParsedLine[];
};
export type ParseResult = { template_id: string; template_name: string; forwarder: string; tickets: ParsedTicket[]; issues: ParseIssue[] };

async function fail(res: Response): Promise<never> {
  let msg = res.statusText || `HTTP ${res.status}`;
  try {
    const j = (await res.json()) as { detail?: unknown };
    if (typeof j.detail === "string") msg = j.detail;
  } catch {
    // ignore
  }
  throw new ApiError(res.status, msg);
}

export async function fetchInvoiceTemplates(): Promise<InvoiceTemplateInfo[]> {
  const res = await fetch(resolveApiUrl("/api/invoice-templates"));
  if (!res.ok) await fail(res);
  return ((await res.json()) as { templates: InvoiceTemplateInfo[] }).templates;
}

export async function detectInvoiceTemplate(file: File): Promise<DetectResult> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(resolveApiUrl("/api/invoice-templates/detect"), { method: "POST", body: fd });
  if (!res.ok) await fail(res);
  return (await res.json()) as DetectResult;
}

export async function parseInvoiceTemplate(
  file: File,
  templateId: string,
  csvFiles: File[],
  accept: string[] = [],
): Promise<ParseResult> {
  const fd = new FormData();
  fd.append("file", file);
  if (templateId) fd.append("template_id", templateId);
  csvFiles.forEach((f) => fd.append("csv_files", f));
  if (accept.length) fd.append("accept", JSON.stringify(accept));
  const res = await fetch(resolveApiUrl("/api/invoice-templates/parse"), { method: "POST", body: fd });
  if (!res.ok) await fail(res);
  return (await res.json()) as ParseResult;
}
