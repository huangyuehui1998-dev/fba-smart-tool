import type { HistoryFileItem } from "@/lib/api/history-files";
import {
  createMockHistoryFile,
  fetchHistoryFileAsFile,
  resolveHistoryFileAsFile,
} from "@/lib/api/history-files";

function cacheKey(kind: "csv" | "pdf", item: HistoryFileItem): string {
  return `${kind}:${item.id}:${item.name}`;
}

const fileCache = new Map<string, File>();
const inflight = new Map<string, Promise<File>>();
const prefetchedKeys = new Set<string>();

async function loadHistoryFile(
  kind: "csv" | "pdf",
  item: HistoryFileItem,
  skipNetworkForMock = false,
): Promise<File> {
  if (item.source === "mock" && skipNetworkForMock) {
    return createMockHistoryFile(kind, item.name);
  }
  return resolveHistoryFileAsFile(kind, item);
}

export function getCachedHistoryFile(kind: "csv" | "pdf", item: HistoryFileItem): File | undefined {
  return fileCache.get(cacheKey(kind, item));
}

/** 带内存缓存的历史文件解析；并发请求同一文件时复用 Promise。 */
export async function getHistoryFileCached(
  kind: "csv" | "pdf",
  item: HistoryFileItem,
  options?: { skipNetworkForMock?: boolean },
): Promise<File> {
  const key = cacheKey(kind, item);
  const cached = fileCache.get(key);
  if (cached) return cached;

  let pending = inflight.get(key);
  if (!pending) {
    pending = loadHistoryFile(kind, item, options?.skipNetworkForMock)
      .then((file) => {
        fileCache.set(key, file);
        inflight.delete(key);
        return file;
      })
      .catch((err) => {
        inflight.delete(key);
        throw err;
      });
    inflight.set(key, pending);
  }
  return pending;
}

async function prefetchOne(
  kind: "csv" | "pdf",
  item: HistoryFileItem,
  skipNetworkForMock: boolean,
): Promise<void> {
  const key = cacheKey(kind, item);
  if (fileCache.has(key) || prefetchedKeys.has(key)) return;
  prefetchedKeys.add(key);
  try {
    await getHistoryFileCached(kind, item, { skipNetworkForMock });
  } catch {
    prefetchedKeys.delete(key);
  }
}

/** 后台预取历史文件，点击时通常可即时命中缓存。 */
export function prefetchHistoryFiles(
  kind: "csv" | "pdf",
  items: HistoryFileItem[],
  options?: { skipNetworkForMock?: boolean; concurrency?: number },
): void {
  if (!items.length || typeof window === "undefined") return;

  const skipNetworkForMock = options?.skipNetworkForMock ?? false;
  const concurrency = Math.max(1, options?.concurrency ?? (kind === "pdf" ? 3 : 4));
  const queue = items.filter((item) => {
    const key = cacheKey(kind, item);
    return !fileCache.has(key) && !prefetchedKeys.has(key);
  });
  if (!queue.length) return;

  let index = 0;
  const worker = async () => {
    while (index < queue.length) {
      const item = queue[index++];
      await prefetchOne(kind, item, skipNetworkForMock);
    }
  };

  void Promise.all(Array.from({ length: Math.min(concurrency, queue.length) }, () => worker()));
}

export function primeHistoryFileCache(kind: "csv" | "pdf", item: HistoryFileItem, file: File): void {
  fileCache.set(cacheKey(kind, item), file);
}

export function clearHistoryFileCache(): void {
  fileCache.clear();
  inflight.clear();
  prefetchedKeys.clear();
}

/** 直接拉取（不走 resolve 的 mock 回退），供需要时使用。 */
export { fetchHistoryFileAsFile };
