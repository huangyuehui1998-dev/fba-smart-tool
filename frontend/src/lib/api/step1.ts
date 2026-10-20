import { apiPostJson, apiUpload, downloadBlob } from "./client";
import type {
  ApiSkuRow,
  ComputePreviewResponse,
  ParseRowsResponse,
  ValidateInputResponse,
} from "@/types/step1";

export type * from "@/types/step1";

export function parseTextLocal(text: string) {
  return apiPostJson<ParseRowsResponse>("/api/parse_text", { text });
}

export function parseTextDeepseek(
  text: string,
  options?: { apiKey?: string; model?: string; temperature?: number },
) {
  return apiPostJson<ParseRowsResponse>("/api/parse_text/deepseek", {
    text,
    api_key: options?.apiKey || undefined,
    model: options?.model || undefined,
    temperature: options?.temperature,
  });
}

export function parseExcelFile(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiUpload<ParseRowsResponse>("/api/parse_excel", form);
}

export function computePreview(rows: ApiSkuRow[], throwRatio?: number) {
  return apiPostJson<ComputePreviewResponse>("/api/compute_preview", {
    rows,
    ...(throwRatio != null ? { throw_ratio: throwRatio } : {}),
  });
}

export function validateInput(rows: ApiSkuRow[]) {
  return apiPostJson<ValidateInputResponse>("/api/validate_input", { rows });
}

export function downloadInputTemplate() {
  return downloadBlob("/api/input_template", "发货录入样表.xlsx");
}
