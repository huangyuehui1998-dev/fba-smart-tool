import { describe, expect, it } from "vitest";

import { DECLARED_VALUE_CFR_NOTE, NET_RATIO_NOTICE, NET_WEIGHT_MODE_NOTICE } from "./customs-notices";

describe("step5 fixed notices", () => {
  it("keeps the 19 CFR declared-value note", () => {
    expect(DECLARED_VALUE_CFR_NOTE).toContain("19 CFR 141.86");
    expect(DECLARED_VALUE_CFR_NOTE).toContain("高报");
  });

  it("explains the new default net-weight mode", () => {
    expect(NET_WEIGHT_MODE_NOTICE).toContain("tare_from_carton");
    expect(NET_WEIGHT_MODE_NOTICE).toContain("原 ratio 口径仍可在设置中切换");
    expect(NET_RATIO_NOTICE).toBe("比例法无法规依据，非规范口径");
  });
});
