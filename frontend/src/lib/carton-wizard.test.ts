import { describe, expect, it } from "vitest";
import { cartonWizardPayload, cartonWizardReview, cartonWizardStepBlockers, toCm } from "@/lib/carton-wizard";

describe("carton wizard", () => {
  it("blocks each step until its required fields are filled", () => {
    const empty = {
      sku: "",
      unit: "cm" as const,
      length: "",
      width: "",
      height: "",
      qty: "",
      gross: "",
      tare: "",
      unitWeight: "",
    };
    expect(cartonWizardStepBlockers(empty, 0)).toEqual(["请填写 SKU"]);
    expect(cartonWizardStepBlockers({ ...empty, sku: "BOX-1" }, 0)).toEqual([]);
    expect(cartonWizardStepBlockers({ ...empty, sku: "BOX-1" }, 1)).toEqual(["请填写长度", "请填写宽度", "请填写高度"]);
    expect(
      cartonWizardStepBlockers({ ...empty, sku: "BOX-1", length: "10", width: "10", height: "10" }, 1),
    ).toEqual([]);
    expect(
      cartonWizardStepBlockers({ ...empty, sku: "BOX-1", length: "10", width: "10", height: "10" }, 2),
    ).toEqual(["单箱数量必须是大于 0 的整数", "请填写单箱毛重"]);
  });

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

  it("blocks gross weight above the 70kg API limit", () => {
    const review = cartonWizardReview({
      sku: "BOX-1",
      unit: "cm",
      length: "40",
      width: "40",
      height: "40",
      qty: "1",
      gross: "80",
      tare: "",
      unitWeight: "",
    });
    expect(review.blockers.some((item) => item.includes("70"))).toBe(true);
    expect(review.warnings.some((item) => item.includes("23"))).toBe(false);
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
