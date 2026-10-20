export const DEEPSEEK_KEY_STORAGE = "fba_deepseek_api_key";
export const DEEPSEEK_MODEL_STORAGE = "fba_deepseek_model";
export const DEEPSEEK_TEMPERATURE_STORAGE = "fba_deepseek_temperature";
export const SIDEBAR_OPEN_STORAGE = "fba_sidebar_open";
/** 布局偏好版本：v2 起侧边栏默认收起，首次读取前忽略旧 open 标记 */
const SIDEBAR_LAYOUT_VERSION = "fba_sidebar_layout_v2";
/** @deprecated 兼容旧版「完全隐藏」标记 */
const SIDEBAR_HIDDEN_STORAGE = "fba_sidebar_hidden";

export const DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash";
export const DEFAULT_DEEPSEEK_TEMPERATURE = 0.1;

export const DEEPSEEK_MODEL_OPTIONS = [
  { value: "deepseek-v4-flash", label: "deepseek-v4-flash（高速 · 高性价比，默认）" },
  { value: "deepseek-v4-pro", label: "deepseek-v4-pro（复杂推理）" },
] as const;

export type DeepseekModel = (typeof DEEPSEEK_MODEL_OPTIONS)[number]["value"];

export interface DeepseekOptions {
  apiKey: string;
  model: DeepseekModel;
  temperature: number;
}

function readStorage(key: string): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(key) ?? "";
}

export function getDeepseekApiKey(): string {
  return "";
}

export async function saveDeepseekKey(key: string): Promise<void> {
  await fetch("/api/settings/deepseek-key", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
}

export function getDeepseekModel(): DeepseekModel {
  const stored = readStorage(DEEPSEEK_MODEL_STORAGE);
  if (DEEPSEEK_MODEL_OPTIONS.some((m) => m.value === stored)) {
    return stored as DeepseekModel;
  }
  return DEFAULT_DEEPSEEK_MODEL;
}

export function getDeepseekTemperature(): number {
  const raw = readStorage(DEEPSEEK_TEMPERATURE_STORAGE);
  if (!raw) return DEFAULT_DEEPSEEK_TEMPERATURE;
  const n = Number.parseFloat(raw);
  if (Number.isNaN(n)) return DEFAULT_DEEPSEEK_TEMPERATURE;
  return Math.min(2, Math.max(0, n));
}

export function getDeepseekOptions(): DeepseekOptions {
  return {
    apiKey: getDeepseekApiKey(),
    model: getDeepseekModel(),
    temperature: getDeepseekTemperature(),
  };
}

const SIDEBAR_CHANGE_EVENT = "fba_sidebar_change";

export function isSidebarOpen(): boolean {
  if (readStorage(SIDEBAR_LAYOUT_VERSION) !== "1") {
    return false;
  }
  return readStorage(SIDEBAR_OPEN_STORAGE) === "1";
}

export function setSidebarOpen(open: boolean): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(SIDEBAR_LAYOUT_VERSION, "1");
    localStorage.setItem(SIDEBAR_OPEN_STORAGE, open ? "1" : "0");
    localStorage.removeItem(SIDEBAR_HIDDEN_STORAGE);
    window.dispatchEvent(new Event(SIDEBAR_CHANGE_EVENT));
  } catch {
    // quota / 隐私模式 — 忽略
  }
}

/** 供 useSyncExternalStore 订阅侧边栏展开状态。 */
export function subscribeSidebarOpen(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") return () => undefined;
  const handler = () => onStoreChange();
  window.addEventListener(SIDEBAR_CHANGE_EVENT, handler);
  window.addEventListener("storage", handler);
  return () => {
    window.removeEventListener(SIDEBAR_CHANGE_EVENT, handler);
    window.removeEventListener("storage", handler);
  };
}

export function getSidebarOpenSnapshot(): boolean {
  return isSidebarOpen();
}
