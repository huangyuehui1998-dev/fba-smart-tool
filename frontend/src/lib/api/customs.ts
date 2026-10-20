import { apiFetchJson, apiPostJson, resolveApiUrl, ApiError } from "@/lib/api/client";

export type CustomsSource = "invoice" | "shipment";

export interface CustomsLineItem {
  seq: number;
  chinese_name: string;
  hs_code: string;
  qty: number;
  unit: string;
  unit_price: number;
  amount: number;
  brand: string;
  model: string;
  brand_type: string;
  export_preferential: string;
  declare_elements: string;
  quarantine_code: string;
  box_count: number;
  gross_kg: number;
  net_kg: number;
  origin_country: string;
  dest_country: string;
  source_place: string;
  tax_exemption: string;
  price_source?: string;
}

export interface CustomsNotice {
  code: string;
  skus: string[];
  message: string;
}

export interface CustomsPriceSource {
  sku: string;
  price: number | null;
  source: string;
  source_label: string;
}

export interface CustomsPackageData {
  exporter: Record<string, string>;
  order_no: string;
  buyer: string;
  trade_term: string;
  declared_value_basis?: string;
  fx_rate?: number | null;
  fx_rate_type?: string;
  fx_applicable_month?: string;
  fx_source_url?: string;
  fx_publish_date?: string;
  net_weight_mode?: string;
  package_type: string;
  total_pieces: number;
  total_gross_kg: number;
  total_net_kg: number;
  total_qty: number;
  total_amount: number;
  remarks: string;
  lines: CustomsLineItem[];
  dates: Record<string, string>;
  amount_in_words: string;
  main_goods_name: string;
  hs_codes_summary: string;
  source: CustomsSource;
  dest_country?: string;
  price_sources?: CustomsPriceSource[];
  warnings?: CustomsNotice[];
  blocking?: CustomsNotice[];
  shipment_ids?: string[];
  declare_mode?: string;
}

export interface CustomsPreviewPayload {
  source: CustomsSource;
  exporter_id?: string;
  order_no: string;
  dates?: Record<string, string>;
  overrides?: Record<string, unknown>;
  workflow_json?: Record<string, unknown>;
  invoice_draft?: Record<string, unknown> | null;
  selected_shipment_ids?: string[];
}

export function previewCustoms(body: CustomsPreviewPayload) {
  return apiPostJson<{ ok: boolean; data: CustomsPackageData }>("/api/customs/preview", body);
}

export async function exportCustomsBlob(
  body: CustomsPreviewPayload & { data?: CustomsPackageData; export_format?: "xlsx" | "xls" },
) {
  const res = await fetch(resolveApiUrl("/api/customs/export"), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "*/*" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const err = (await res.json()) as { detail?: string };
      if (err.detail) message = err.detail;
    } catch {
      // ignore
    }
    throw new Error(message);
  }
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const match = /filename\*?=(?:UTF-8''|"?)([^";]+)/i.exec(cd);
  const filename = match ? decodeURIComponent(match[1].replace(/"/g, "")) : "报关资料.xlsx";
  return { blob, filename };
}

export async function triggerDownload(blob: Blob, filename: string) {
  const { triggerBrowserDownload } = await import("./client");
  await triggerBrowserDownload(blob, filename);
}
