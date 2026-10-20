import { apiFetchJson, apiPostJson, resolveApiUrl, ApiError } from "@/lib/api/client";

export interface ForwarderProfile {
  id: string;
  name: string;
  template_file: string;
  header_row: number;
  first_data_row: number;
  column_map: Record<string, number>;
  created_at?: string;
  group_logic?: string;
  unit_conversion?: Record<string, string>;
  columns_mapping?: Record<string, unknown>;
  has_mapping_engine?: boolean;
}

export function fetchForwarders() {
  return apiFetchJson<{ forwarders: ForwarderProfile[] }>("/api/forwarders");
}

export function createForwarder(name: string, templateBase64: string) {
  return apiPostJson<{ ok: boolean; forwarder: ForwarderProfile }>("/api/forwarders", {
    name,
    template_base64: templateBase64,
  });
}

export function deleteForwarder(forwarderId: string) {
  return apiFetchJson<{ ok: boolean }>(`/api/forwarders/${encodeURIComponent(forwarderId)}`, {
    method: "DELETE",
  });
}

export async function fetchForwarderTemplateBlob(forwarderId: string): Promise<Blob> {
  const res = await fetch(resolveApiUrl(`/api/forwarders/${encodeURIComponent(forwarderId)}/template`), {
    headers: { Accept: "*/*" },
  });
  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, message);
  }
  return res.blob();
}
