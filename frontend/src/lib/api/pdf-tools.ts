import { ApiError, resolveApiUrl } from "@/lib/api/client";
import {
  advancedOptionsToApiPayload,
  type PdfLabelAdvancedOptions,
} from "@/lib/pdf-label-advanced-options";

export interface PdfLabelSize {
  key: string;
  name: string;
  width_mm: number;
  height_mm: number;
}

export type PdfConvertOptions = {
  sizeKey?: string;
  widthMm?: number;
  heightMm?: number;
  advanced?: PdfLabelAdvancedOptions;
  onProgress?: (percent: number, message: string) => void;
};

export function fetchPdfLabelSizes() {
  return import("@/lib/api/client").then(({ apiFetchJson }) =>
    apiFetchJson<{ sizes: PdfLabelSize[] }>("/api/pdf/sizes"),
  );
}

async function triggerBrowserDownload(blob: Blob, filename: string): Promise<void> {
  const { triggerBrowserDownload: sharedTrigger } = await import("./client");
  await sharedTrigger(blob, filename);
}

function base64ToPdfBlob(b64: string): Blob {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type: "application/pdf" });
}

type SseFilePayload = {
  filename: string;
  pdf_base64: string;
};

type SsePayload = {
  event?: string;
  progress?: number;
  message?: string;
  filename?: string;
  pdf_base64?: string;
  files?: SseFilePayload[];
};

async function downloadResultFiles(payload: SsePayload) {
  if (payload.files?.length) {
    for (const [index, file] of payload.files.entries()) {
      await triggerBrowserDownload(
        base64ToPdfBlob(file.pdf_base64),
        file.filename || `标签转换_${index + 1}.pdf`,
      );
    }
    return;
  }
  if (payload.pdf_base64) {
    await triggerBrowserDownload(
      base64ToPdfBlob(payload.pdf_base64),
      payload.filename || "标签转换结果.pdf",
    );
  }
}

function parseSseBlocks(
  blocks: string[],
  onProgress: PdfConvertOptions["onProgress"],
  onComplete: (payload: SsePayload) => void,
  onError: (message: string) => void,
) {
  for (const block of blocks) {
    if (!block.trim() || block.startsWith(":")) continue;
    for (const line of block.split("\n")) {
      if (!line.startsWith("data: ")) continue;
      let payload: SsePayload;
      try {
        payload = JSON.parse(line.slice(6)) as SsePayload;
      } catch {
        continue;
      }
      if (payload.event === "error" && payload.message) {
        onError(payload.message);
        return;
      }
      if (payload.progress != null && payload.message) {
        onProgress?.(payload.progress, payload.message);
      }
      if (payload.event === "complete") {
        onComplete(payload);
      }
    }
  }
}

/** PDF 标签 SSE 转换超时（含上传 + 处理 + 下载）。 */
const PDF_CONVERT_TIMEOUT_MS = 10 * 60 * 1000;

async function assertBackendReachable(): Promise<void> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 5000);
  try {
    const res = await fetch(resolveApiUrl("/api/health"), {
      signal: controller.signal,
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      throw new ApiError(res.status, `后端不可用（HTTP ${res.status}）`);
    }
  } catch (err) {
    if (err instanceof ApiError) throw err;
    throw new ApiError(
      0,
      "无法连接后端 API。请确认已运行 scripts/start_dev.ps1，且 Vite 代理端口与 .dev/ports.json 一致。",
    );
  } finally {
    window.clearTimeout(timer);
  }
}

/** 通过 SSE 流式转换，实时接收后端并行处理进度。 */
export async function convertLabelPdfs(files: File[], options: PdfConvertOptions = {}): Promise<void> {
  const {
    sizeKey = "carton_100x100",
    widthMm,
    heightMm,
    advanced,
    onProgress,
  } = options;

  await assertBackendReachable();

  const form = new FormData();
  for (const f of files) form.append("files", f);
  form.append("size_key", sizeKey);
  if (widthMm && widthMm > 0) form.append("width_mm", String(widthMm));
  if (heightMm && heightMm > 0) form.append("height_mm", String(heightMm));
  if (advanced) {
    const payload = advancedOptionsToApiPayload(advanced);
    form.append("padding_mm", String(payload.padding_mm));
    form.append("ignore_top_mm", String(payload.ignore_top_mm));
    form.append("ignore_bottom_mm", String(payload.ignore_bottom_mm));
    form.append("detect_dpi", String(payload.detect_dpi));
    if (payload.custom_text) {
      form.append("custom_text", String(payload.custom_text));
    }
  }

  onProgress?.(0, "准备上传 PDF…");

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), PDF_CONVERT_TIMEOUT_MS);

  let res: Response;
  try {
    res = await fetch(resolveApiUrl("/api/pdf/convert_labels/stream"), {
      method: "POST",
      body: form,
      signal: controller.signal,
      headers: { Accept: "text/event-stream" },
    });
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError(0, "处理超时，请降低「墨迹检测精度」或减少文件数量后重试");
    }
    throw new ApiError(0, "网络错误，请确认后端已启动且 Vite 代理端口正确");
  }

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, message);
  }

  if (!res.body) {
    throw new ApiError(0, "浏览器不支持流式响应");
  }

  onProgress?.(5, "上传完成，服务器正在处理…");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const handleComplete = (payload: SsePayload) => {
    const count = payload.files?.length ?? (payload.pdf_base64 ? 1 : 0);
    onProgress?.(100, count > 1 ? `转换完成，开始下载 ${count} 个文件…` : "转换完成，开始下载…");
    downloadResultFiles(payload);
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() ?? "";
      parseSseBlocks(
        blocks,
        onProgress,
        handleComplete,
        (message) => {
          throw new ApiError(0, message);
        },
      );
    }
    if (buffer.trim()) {
      parseSseBlocks(
        [buffer],
        onProgress,
        handleComplete,
        (message) => {
          throw new ApiError(0, message);
        },
      );
    }
  } finally {
    window.clearTimeout(timer);
  }
}

export function downloadThermalLabels(
  shipments: { pdf_base64: string }[],
  options: PdfConvertOptions = {},
) {
  const pdf_base64 = shipments.map((s) => s.pdf_base64).filter(Boolean);
  options.onProgress?.(20, "正在提交箱唛 PDF…");
  return import("@/lib/api/client").then(async ({ downloadPostBlob }) => {
    options.onProgress?.(50, "正在智能裁剪标签…");
    await downloadPostBlob(
      "/api/pdf/thermal_labels",
      {
        pdf_base64,
        size_key: options.sizeKey ?? "carton_100x100",
        width_mm: options.widthMm,
        height_mm: options.heightMm,
        ...(options.advanced ? advancedOptionsToApiPayload(options.advanced) : {}),
      },
      "10x10热敏箱贴.pdf",
    );
    options.onProgress?.(100, "下载完成");
  });
}
