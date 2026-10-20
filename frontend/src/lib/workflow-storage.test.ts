import { describe, expect, it } from "vitest";

import { EMPTY_ROW } from "@/lib/step1-rows";

import { createEmptySnapshot, resolveRestorableStep, type WorkflowSnapshot } from "./workflow-storage";

function snapshot(overrides: Partial<WorkflowSnapshot>): WorkflowSnapshot {
  return { ...createEmptySnapshot(), ...overrides };
}

describe("resolveRestorableStep", () => {
  it("returns step 1 for empty snapshot", () => {
    const { step, clamped } = resolveRestorableStep(createEmptySnapshot());
    expect(step).toBe(1);
    expect(clamped).toBe(false);
  });

  it("allows step 2 when input rows exist", () => {
    const s = snapshot({
      step: 2,
      inputRows: [{ ...EMPTY_ROW, sku: "SKU-A" }],
    });
    const { step, clamped } = resolveRestorableStep(s);
    expect(step).toBe(2);
    expect(clamped).toBe(false);
  });

  it("clamps step 4 to 2 when boxing not locked", () => {
    const s = snapshot({
      step: 4,
      inputRows: [{ ...EMPTY_ROW, sku: "SKU-A" }],
      boxLocked: false,
      boxEditorApi: [{ 箱号: 1, 来源: "整箱", SKU简称: "SKU-A", 数量: 10 }],
    });
    const { step, clamped } = resolveRestorableStep(s);
    expect(step).toBe(2);
    expect(clamped).toBe(true);
  });

  it("allows step 3 when box locked with editor data", () => {
    const s = snapshot({
      step: 3,
      inputRows: [{ ...EMPTY_ROW, sku: "SKU-A" }],
      boxLocked: true,
      boxEditorApi: [{ 箱号: 1, 来源: "整箱", SKU简称: "SKU-A", 数量: 10 }],
    });
    const { step, clamped } = resolveRestorableStep(s);
    expect(step).toBe(3);
    expect(clamped).toBe(false);
  });

  it("clamps step 5 to 3 for v1-style drafts without step4Ok", () => {
    const s = snapshot({
      version: 1,
      step: 5,
      inputRows: [{ ...EMPTY_ROW, sku: "SKU-A" }],
      boxLocked: true,
      boxEditorApi: [{ 箱号: 1, 来源: "整箱", SKU简称: "SKU-A", 数量: 10 }],
      step4Ok: false,
      highestReachedStep: undefined,
    });
    const { step, clamped } = resolveRestorableStep(s);
    expect(step).toBe(3);
    expect(clamped).toBe(true);
  });

  it("restores step 5 when step4Ok and watermark exist", () => {
    const s = snapshot({
      step: 5,
      inputRows: [{ ...EMPTY_ROW, sku: "SKU-A" }],
      boxLocked: true,
      boxEditorApi: [{ 箱号: 1, 来源: "整箱", SKU简称: "SKU-A", 数量: 10 }],
      step4Ok: true,
      highestReachedStep: 5,
    });
    const { step, clamped } = resolveRestorableStep(s);
    expect(step).toBe(5);
    expect(clamped).toBe(false);
  });
});
