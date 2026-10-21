import { describe, expect, it } from "vitest";

import { shouldPromptWeightConfirm, weightRowsHash } from "./weight-confirm";

const rows = [{ sku: "TEST_A", totalQty: "4", perBox: "4", unitKg: "", emptyKg: "0.3", grossKg: "1.8" }];

describe("weight confirm hash", () => {
  it("does not prompt again when the snapshot hash is unchanged", () => {
    const hash = weightRowsHash(rows);
    expect(shouldPromptWeightConfirm(rows, hash, true)).toBe(false);
  });

  it("prompts again after the entered gross weight changes", () => {
    const hash = weightRowsHash(rows);
    const changed = [{ ...rows[0], grossKg: "2.0" }];
    expect(shouldPromptWeightConfirm(changed, hash, true)).toBe(true);
  });

  it("stays quiet when nothing requires confirmation", () => {
    expect(shouldPromptWeightConfirm(rows, null, false)).toBe(false);
  });
});
