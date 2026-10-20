import { apiFetchJson, apiPostJson, resolveApiUrl, ApiError } from "@/lib/api/client";

export interface ExporterProfile {
  id: string;
  name: string;
  credit_code: string;
  address: string;
  tel: string;
  signed_at: string;
  domestic_source: string;
  is_active?: boolean;
}

export function fetchExporters() {
  return apiFetchJson<{ profiles: ExporterProfile[] }>("/api/exporters");
}

export function upsertExporter(id: string, body: Omit<ExporterProfile, "id" | "is_active">) {
  return apiFetchJson<{ ok: boolean; profile: ExporterProfile }>(`/api/exporters/${encodeURIComponent(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function deleteExporter(id: string) {
  return apiFetchJson<{ ok: boolean }>(`/api/exporters/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function setActiveExporter(id: string) {
  return apiPostJson<{ ok: boolean; profile: ExporterProfile }>("/api/exporters/active", { id });
}

export function newExporterId(name: string) {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^\w\u4e00-\u9fff-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || `exp_${Date.now()}`;
}
