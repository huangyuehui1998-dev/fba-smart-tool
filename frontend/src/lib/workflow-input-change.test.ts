import { describe, expect, it } from "vitest";

import { EMPTY_ROW, type Row } from "@/lib/step1-rows";

import {
  shouldUnlockBoxingOnInputField,
  stageInvalidatedByInputField,
} from "./workflow-input-change";

describe("stageInvalidatedByInputField", () => {
  it("marks boxing chain stale for quantity and carton fields", () => {
    expect(stageInvalidatedByInputField("totalQty")).toBe("input");
    expect(stageInvalidatedByInputField("l")).toBe("input");
    expect(stageInvalidatedByInputField("sku")).toBe("input");
  });

  it("does not unlock boxing for FNSKU-only edits", () => {
    expect(stageInvalidatedByInputField("fnsku")).toBe("export");
    expect(shouldUnlockBoxingOnInputField("fnsku")).toBe(false);
  });

  it("unlocks boxing for material fields", () => {
    const keys: (keyof Row)[] = ["sku", "totalQty", "perBox", "l", "w", "h", "unitKg", "emptyKg", "grossKg"];
    for (const key of keys) {
      expect(shouldUnlockBoxingOnInputField(key)).toBe(true);
    }
  });

  it("empty row keys stay typed", () => {
    expect(EMPTY_ROW.fnsku).toBe("");
  });
});
