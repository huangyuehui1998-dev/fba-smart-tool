import { apiFetchJson, resolveApiUrl } from "./client";

export interface HistoryFileItem {
  id: string;
  name: string;
  size_bytes: number;
  source: string;
}

export interface HistoryFilesResponse {
  csv: HistoryFileItem[];
  pdf: HistoryFileItem[];
  history_dir?: string;
}

/** 后端不可用时的前端占位（与 backend history_files 中 Mock 对齐） */
export const MOCK_HISTORY_FILES: HistoryFilesResponse = {
  csv: [
    { id: "mock-csv-a", name: "测试装箱单_A.csv", size_bytes: 12840, source: "mock" },
    { id: "mock-csv-b", name: "测试装箱单_B.csv", size_bytes: 9560, source: "mock" },
    { id: "mock-csv-c", name: "亚马逊FBA表1.csv", size_bytes: 11200, source: "mock" },
  ],
  pdf: [
    { id: "mock-pdf-a", name: "箱唛_FWA4.pdf", size_bytes: 245760, source: "mock" },
    { id: "mock-pdf-b", name: "箱唛_ORF2.pdf", size_bytes: 198400, source: "mock" },
    { id: "mock-pdf-c", name: "箱唛_GYR2.pdf", size_bytes: 210880, source: "mock" },
  ],
};

export function fetchHistoryFiles(): Promise<HistoryFilesResponse> {
  return apiFetchJson<HistoryFilesResponse>("/api/history/files");
}

function historyDownloadUrl(kind: "csv" | "pdf", name: string): string {
  const qs = new URLSearchParams({ kind, name });
  return resolveApiUrl(`/api/history/files/download?${qs.toString()}`);
}

/** 拉取历史文件并转为浏览器 File，与真实上传等价。 */
export async function fetchHistoryFileAsFile(
  kind: "csv" | "pdf",
  name: string,
): Promise<File> {
  const url = historyDownloadUrl(kind, name);
  let res: Response;
  try {
    res = await fetch(url, {
      headers: { Accept: "*/*" },
    });
  } catch (err) {
    throw new Error(`无法加载历史文件 ${name}：${err instanceof Error ? err.message : "网络错误"}`);
  }
  if (!res.ok) {
    throw new Error(`无法加载历史文件 ${name}（HTTP ${res.status}）`);
  }
  const blob = await res.blob();
  if (!blob.size) {
    throw new Error(`历史文件 ${name} 为空`);
  }
  const type = kind === "csv" ? "text/csv" : "application/pdf";
  try {
    return new File([blob], name, { type, lastModified: Date.now() });
  } catch (err) {
    throw new Error(`无法构造文件 ${name}：${err instanceof Error ? err.message : "浏览器不支持 File API"}`);
  }
}

/** Mock 条目无后端字节时，生成最小可用占位 File。 */
export function createMockHistoryFile(kind: "csv" | "pdf", name: string): File {
  const body =
    kind === "csv"
      ? "SKU,Title,Quantity\nMOCK-SKU,Placeholder,1\n"
      : "%PDF-1.4\n% Mock label PDF\n";
  const type = kind === "csv" ? "text/csv" : "application/pdf";
  return new File([body], name, { type, lastModified: Date.now() });
}

export async function resolveHistoryFileAsFile(
  kind: "csv" | "pdf",
  item: HistoryFileItem,
): Promise<File> {
  if (item.source === "mock") {
    try {
      return await fetchHistoryFileAsFile(kind, item.name);
    } catch {
      return createMockHistoryFile(kind, item.name);
    }
  }
  return fetchHistoryFileAsFile(kind, item.name);
}
