import { toast } from "sonner";

import {
  isAbortError,
  notifyDownloadCancelled,
  notifyDownloadStarted,
} from "@/lib/task-save-feedback";
const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";

/** JSON API 默认超时，避免后端僵死时页面永久「加载中」。 */
const JSON_FETCH_TIMEOUT_MS = 30_000;

function jsonFetchSignal(init?: RequestInit): AbortSignal | undefined {
  if (init?.signal) return init.signal;
  if (typeof AbortSignal !== "undefined" && "timeout" in AbortSignal) {
    return AbortSignal.timeout(JSON_FETCH_TIMEOUT_MS);
  }
  return undefined;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function resolveUrl(path: string): string {
  if (path.startsWith("http")) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

/** 供其他 API 模块复用（与 apiFetchJson 同源策略一致）。 */
export function resolveApiUrl(path: string): string {
  return resolveUrl(path);
}

function readableErrorText(value: unknown): string {
  if (typeof value === "string") return value.trim();
  if (Array.isArray(value)) return value.map(String).join("; ");
  if (value && typeof value === "object") {
    const obj = value as { message?: unknown; detail?: unknown };
    const message = readableErrorText(obj.message);
    if (message) return message;
    if (typeof obj.detail === "string") return obj.detail.trim();
  }
  return "";
}

function statusFallback(res: Response): string {
  const text = (res.statusText || "").trim();
  if (/^unprocessable\b/i.test(text)) return "请求没有完成";
  return text || `HTTP ${res.status}`;
}

function withErrorContext(body: unknown, detail: unknown): unknown {
  if (!body || typeof body !== "object") return detail;
  const extra = body as { address?: unknown; code?: unknown; warehouse_candidates?: unknown };
  const address = typeof extra.address === "string" ? extra.address : "";
  const code = typeof extra.code === "string" ? extra.code : "";
  const candidates = Array.isArray(extra.warehouse_candidates) ? extra.warehouse_candidates : undefined;
  if (!address && !code && !candidates) return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const obj = detail as { address?: unknown; code?: unknown; warehouse_candidates?: unknown };
    return {
      ...obj,
      ...(address ? { address: typeof obj.address === "string" && obj.address ? obj.address : address } : {}),
      ...(code ? { code: typeof obj.code === "string" && obj.code ? obj.code : code } : {}),
      ...(candidates ? { warehouse_candidates: obj.warehouse_candidates ?? candidates } : {}),
    };
  }
  return {
    detail,
    message: typeof detail === "string" ? detail : undefined,
    ...(address ? { address } : {}),
    ...(code ? { code } : {}),
    ...(candidates ? { warehouse_candidates: candidates } : {}),
  };
}

async function parseErrorResponse(res: Response): Promise<{ message: string; detail: unknown }> {
  const fallback = statusFallback(res);
  try {
    const body = await res.json();
    const detail = body?.detail ?? body;
    const message = readableErrorText(detail) || readableErrorText(body?.message) || fallback;
    return { message, detail: withErrorContext(body, detail) };
  } catch {
    return { message: fallback, detail: undefined };
  }
}

function isJsonContentType(contentType: string): boolean {
  return contentType.includes("application/json") || contentType.includes("+json");
}

function isFileContentType(contentType: string): boolean {
  const lower = contentType.toLowerCase();
  return (
    lower.includes("application/vnd.openxmlformats") ||
    lower.includes("application/vnd.ms-excel") ||
    lower.includes("application/octet-stream") ||
    lower.includes("application/pdf") ||
    lower.includes("application/zip") ||
    lower.includes("text/csv")
  );
}

/** 仅用于期望 JSON 的 API（上传、校验、查询等），绝不触发浏览器下载。 */
export async function apiFetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const signal = jsonFetchSignal(init);
  let res: Response;
  try {
    res = await fetch(resolveUrl(path), {
      ...init,
      signal,
      headers: {
        Accept: "application/json",
        ...init?.headers,
      },
    });
  } catch (err) {
    if (err instanceof Error && err.name === "TimeoutError") {
      throw new ApiError(
        0,
        "请求超时：后端未响应，请确认服务已启动（或重启后端后再试）",
      );
    }
    throw err;
  }
  if (!res.ok) {
    const parsed = await parseErrorResponse(res);
    throw new ApiError(res.status, parsed.message, parsed.detail);
  }
  const contentType = res.headers.get("content-type") ?? "";
  if (!isJsonContentType(contentType)) {
    throw new ApiError(
      res.status,
      "接口返回了文件而非 JSON，请确认未误调用导出接口",
    );
  }
  return (await res.json()) as T;
}

/** @deprecated 请使用 apiFetchJson；保留别名避免遗漏引用。 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  return apiFetchJson<T>(path, init);
}

export async function apiPutJson<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  return apiFetchJson<T>(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...init?.headers },
    body: JSON.stringify(body),
    ...init,
  });
}

export async function apiPostJson<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  return apiFetchJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...init?.headers },
    body: JSON.stringify(body),
    ...init,
  });
}

export async function apiPatchJson<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  return apiFetchJson<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...init?.headers },
    body: JSON.stringify(body),
    ...init,
  });
}

export async function apiUpload<T>(
  path: string,
  formData: FormData,
  init?: RequestInit,
): Promise<T> {
  return apiFetchJson<T>(path, {
    method: "POST",
    body: formData,
    ...init,
  });
}


export async function triggerBrowserDownload(blob: Blob, filename: string): Promise<void> {
  let savedLocally = false;

  if ('showSaveFilePicker' in window) {
    try {
      const ext = filename.split('.').pop()?.toLowerCase();
      let types: any[] = [];
      if (ext === 'xlsx') {
        types = [{ description: 'Excel Files', accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] } }];
      } else if (ext === 'pdf') {
        types = [{ description: 'PDF Files', accept: { 'application/pdf': ['.pdf'] } }];
      } else if (ext === 'zip') {
        types = [{ description: 'ZIP Archives', accept: { 'application/zip': ['.zip'] } }];
      } else {
        types = [{ description: 'All Files', accept: { '*/*': ['.' + (ext || '*')] } }];
      }

      const fileHandle = await (window as any).showSaveFilePicker({
        suggestedName: filename,
        types: types,
      });
      const writable = await fileHandle.createWritable();
      await writable.write(blob);
      await writable.close();
      savedLocally = true;
    } catch (err: unknown) {
      if (isAbortError(err)) {
        notifyDownloadCancelled(filename);
        return;
      }
      console.warn("showSaveFilePicker failed, falling back to standard download:", err);
    }
  }

  if (savedLocally) {
    toast.success(`文件保存成功：${filename}`, {
      description: "您可以在软件内部直接点击打开，或去保存目录双击打开。",
      duration: 8000,
      action: {
        label: "在浏览器中打开",
        onClick: () => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = filename;
          a.click();
          URL.revokeObjectURL(url);
        }
      }
    });
    return;
  }

  notifyDownloadStarted(filename);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function readDownloadBlob(res: Response): Promise<Blob> {
  const contentType = res.headers.get("content-type") ?? "";
  if (isJsonContentType(contentType)) {
    const parsed = await parseErrorResponse(res);
    throw new ApiError(res.status, parsed.message, parsed.detail);
  }
  if (contentType && !isFileContentType(contentType)) {
    throw new ApiError(res.status, `意外的响应类型：${contentType}`);
  }
  return res.blob();
}

export async function downloadUploadBlob(
  path: string,
  formData: FormData,
  filename: string,
): Promise<void> {
  const res = await fetch(resolveUrl(path), {
    method: "POST",
    body: formData,
    headers: { Accept: "*/*" },
  });
  if (!res.ok) {
    let detail: unknown;
    let message = res.statusText || `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail ?? body;
      if (typeof detail === "string") message = detail;
      else if (detail && typeof detail === "object" && "message" in detail) {
        message = String((detail as { message: string }).message);
      }
    } catch {
      detail = undefined;
    }
    throw new ApiError(res.status, message, detail);
  }
  const blob = await readDownloadBlob(res);
  await triggerBrowserDownload(blob, filename);
}

/** 显式下载：仅由用户点击「下载」按钮时调用。 */
export async function downloadPostBlob(
  path: string,
  body: unknown,
  filename: string,
): Promise<void> {
  const res = await fetch(resolveUrl(path), {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "*/*" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const parsed = await parseErrorResponse(res);
    throw new ApiError(res.status, parsed.message, parsed.detail);
  }
  const blob = await readDownloadBlob(res);
  await triggerBrowserDownload(blob, filename);
}

export async function downloadBlob(path: string, filename: string): Promise<void> {
  const res = await fetch(resolveUrl(path), {
    method: "GET",
    headers: { Accept: "*/*" },
  });
  if (!res.ok) {
    const parsed = await parseErrorResponse(res);
    throw new ApiError(res.status, parsed.message, parsed.detail);
  }
  const blob = await readDownloadBlob(res);
  await triggerBrowserDownload(blob, filename);
}
