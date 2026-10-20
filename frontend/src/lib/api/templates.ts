import { apiFetchJson, apiUpload, downloadBlob } from "./client";

export interface TemplatesListResponse {
  templates_dir: string;
  files: string[];
}

export interface TemplatePreviewResponse {
  filename: string;
  headers: (string | number | null)[][];
}

export function fetchTemplatesList() {
  return apiFetchJson<TemplatesListResponse>("/api/templates");
}

export function fetchTemplatePreview(filename: string) {
  return apiFetchJson<TemplatePreviewResponse>(
    `/api/templates/preview?name=${encodeURIComponent(filename)}`,
  );
}

export function downloadTemplateFile(filename: string) {
  return downloadBlob(
    `/api/templates/download?name=${encodeURIComponent(filename)}`,
    filename,
  );
}

export function uploadTemplateFile(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiUpload<{ ok: boolean; filename: string; files: string[] }>("/api/templates/upload", form);
}
