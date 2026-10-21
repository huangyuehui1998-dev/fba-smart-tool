import { afterEach, describe, expect, it, vi } from "vitest";

import { DEEPSEEK_KEY_STORAGE, getDeepseekApiKey, saveDeepseekKey } from "@/lib/deepseek-settings";

function installStorage() {
  const bag = new Map<string, string>();
  const storage = {
    getItem: (key: string) => bag.get(key) ?? null,
    setItem: (key: string, value: string) => {
      bag.set(key, value);
    },
    removeItem: (key: string) => {
      bag.delete(key);
    },
    key: (index: number) => Array.from(bag.keys())[index] ?? null,
    get length() {
      return bag.size;
    },
    clear: () => bag.clear(),
  };
  vi.stubGlobal("localStorage", storage);
  vi.stubGlobal("window", { localStorage: storage });
  return bag;
}

describe("deepseek key stays off localStorage", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("never writes the key while saving", async () => {
    const bag = installStorage();
    const secret = "sk-1234567890abcdef1234";
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ status: "已设置" }), { status: 200 })),
    );
    await saveDeepseekKey(secret);
    const dumped = Array.from(bag.entries()).map(([key, value]) => `${key}=${value}`).join("\n");
    expect(bag.has(DEEPSEEK_KEY_STORAGE)).toBe(false);
    expect(dumped.includes(secret)).toBe(false);
    expect(getDeepseekApiKey()).toBe("");
  });
});
