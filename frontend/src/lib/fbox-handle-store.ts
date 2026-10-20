const DB_NAME = "fba_smart_tool";
const DB_VERSION = 1;
const STORE_NAME = "file_handles";
const HANDLE_KEY = "current_project";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onerror = () => reject(request.error ?? new Error("无法打开 IndexedDB"));
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

async function withStore<T>(
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, mode);
    const store = tx.objectStore(STORE_NAME);
    const request = fn(store);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB 操作失败"));
    request.onsuccess = () => resolve(request.result);
    tx.oncomplete = () => db.close();
    tx.onerror = () => reject(tx.error ?? new Error("IndexedDB 事务失败"));
  });
}

export async function storeProjectHandle(handle: FileSystemFileHandle): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  await withStore("readwrite", (store) => store.put(handle, HANDLE_KEY));
}

export async function clearStoredProjectHandle(): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  try {
    await withStore("readwrite", (store) => store.delete(HANDLE_KEY));
  } catch {
    // ignore
  }
}

async function ensureHandlePermission(
  handle: FileSystemFileHandle,
): Promise<FileSystemFileHandle | null> {
  const opts = { mode: "readwrite" as const };
  let permission = await handle.queryPermission(opts);
  if (permission === "prompt") {
    permission = await handle.requestPermission(opts);
  }
  return permission === "granted" ? handle : null;
}

/** 从 IndexedDB 恢复上次工程句柄（需用户已授权读写）。 */
export async function loadStoredProjectHandle(): Promise<FileSystemFileHandle | null> {
  if (typeof indexedDB === "undefined") return null;
  try {
    const handle = await withStore<FileSystemFileHandle | undefined>("readonly", (store) =>
      store.get(HANDLE_KEY),
    );
    if (!handle || handle.kind !== "file") return null;
    return ensureHandlePermission(handle);
  } catch {
    return null;
  }
}
