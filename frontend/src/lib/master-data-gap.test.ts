import { describe, expect, it } from "vitest";

import { masterDataGapBannerText } from "./master-data-gap";

describe("master data gap banner", () => {
  it("names how many SKUs are missing master data", () => {
    const text = masterDataGapBannerText([
      { sku: "TEST_A", missing: ["asin", "unit_dims"] },
      { sku: "TEST_B", missing: ["asin", "name", "unit_dims"] },
    ]);
    expect(text).toContain("2 个 SKU");
    expect(text).toContain("缺 ASIN/品名/单品尺寸");
  });

  it("stays empty when every SKU is complete", () => {
    expect(masterDataGapBannerText([])).toBe("");
  });
});
