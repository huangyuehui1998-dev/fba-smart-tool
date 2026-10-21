import { describe, expect, it } from "vitest";

import { staFeeOutOfRange } from "./sta-fee";

describe("STA fee range", () => {
  it("marks 200 red when the estimate is 63–180", () => {
    expect(staFeeOutOfRange(200, 63, 180)).toBe(true);
    expect(staFeeOutOfRange(63, 63, 180)).toBe(false);
    expect(staFeeOutOfRange(120, 63, 180)).toBe(false);
  });
});
