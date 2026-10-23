import { describe, expect, it } from "vitest";
import { formatCartonCm, formatShippingSheetCell, formatShippingSheetLegendCell } from "@/lib/shipping-sheet";

describe("carton centimeter display", () => {
  it("keeps 44.96 instead of rounding to 45.00", () => {
    expect(formatCartonCm(44.96)).toBe("44.96");
    expect(formatCartonCm(45)).toBe("45");
    expect(formatShippingSheetLegendCell("箱长(cm)", { "箱长(cm)": 44.96 })).toBe("44.96");
    expect(formatShippingSheetCell("外箱长(CM)", { "外箱长(CM)": 44.96 })).toBe("44.96");
  });
});
