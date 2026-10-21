import { describe, expect, it } from "vitest";
import { cartonWizardPayload, cartonWizardReview, toCm } from "@/lib/carton-wizard";

describe("carton wizard", () => {
  it("blocks save when required fields are missing", () => {
    const review = cartonWizardReview({
      sku: "",
      unit: "cm",
      length: "",
      width: "",
      height: "",
      qty: "",
      gross: "",
      tare: "",
      unitWeight: "",
    });
    expect(review.blockers.length).toBeGreaterThan(0);
  });

  it("warns on oversize and overweight without adding a blocker under 70kg", () => {
    const review = cartonWizardReview({
      sku: "BOX-1",
      unit: "cm",
      length: "70",
      width: "40",
      height: "30",
      qty: "10",
      gross: "24",
      tare: "",
      unitWeight: "",
    });
    expect(review.blockers).toEqual([]);
    expect(review.warnings.some((item) => item.includes("63.5"))).toBe(true);
    expect(review.warnings.some((item) => item.includes("23"))).toBe(true);
  });

  it("converts inches to centimeters", () => {
    expect(toCm("10", "in")).toBeCloseTo(25.4);
    const payload = cartonWizardPayload({
      sku: "BOX-1",
      unit: "in",
      length: "10",
      width: "10",
      height: "10",
      qty: "2",
      gross: "3",
      tare: "",
      unitWeight: "",
    });
    expect(payload.length_cm).toBeCloseTo(25.4);
  });
});
