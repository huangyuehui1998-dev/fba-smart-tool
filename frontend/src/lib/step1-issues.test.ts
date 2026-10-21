import { describe, expect, it } from "vitest";

import { summarizeStep1Issues, visibleStep1Indexes } from "@/lib/step1-issues";

describe("step1 issue filter", () => {
  it("matches the uncorrected batch-13 shape: 0 blocks, 2 warnings, 2 rows", () => {
    const summary = summarizeStep1Issues(
      [],
      [
        { row_index: 0, message: "毛重不符" },
        { row_index: 3, message: "毛重不符" },
      ],
    );
    expect(`阻断 ${summary.blockCount}`).toBe("阻断 0");
    expect(`警告 ${summary.warnCount}`).toBe("警告 2");
    expect(visibleStep1Indexes(6, summary, true)).toEqual([0, 3]);
    expect(visibleStep1Indexes(6, summary, true)).toHaveLength(2);
  });
});
