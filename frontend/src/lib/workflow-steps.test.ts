import { describe, expect, it } from "vitest";

import { EMPTY_ROW } from "@/lib/step1-rows";

import {
  canEnterStep,
  getStepBlockReason,
  inferHighestReached,
  type StepGuardState,
} from "./workflow-steps";

function state(overrides: Partial<StepGuardState> = {}): StepGuardState {
  return {
    inputRows: [{ ...EMPTY_ROW, sku: "A", totalQty: "10" }],
    boxLocked: true,
    boxEditorApi: [{ 箱号: 1, 来源: "整箱", SKU简称: "A", 数量: 10 }],
    step4Ok: true,
    highestReachedStep: 1,
    ...overrides,
  };
}

describe("canEnterStep", () => {
  it("allows backward navigation", () => {
    expect(canEnterStep(1, 4, state({ highestReachedStep: 4 }))).toBe(true);
  });

  it("blocks first visit to step 2 without input", () => {
    expect(
      canEnterStep(2, 1, state({ inputRows: [{ ...EMPTY_ROW }], highestReachedStep: 1 })),
    ).toBe(false);
  });

  it("blocks first visit to step 3 without locked plan", () => {
    expect(canEnterStep(3, 1, state({ boxLocked: false, highestReachedStep: 2 }))).toBe(false);
  });

  it("blocks first visit to step 4.5 without step4Ok", () => {
    expect(canEnterStep(4.5, 1, state({ step4Ok: false, highestReachedStep: 4 }))).toBe(false);
  });

  it("allows first visit to step 4 when box locked", () => {
    expect(canEnterStep(4, 1, state({ step4Ok: false, highestReachedStep: 3 }))).toBe(true);
  });

  it("allows revisiting step 4.5 after Step 1 unlocked boxing", () => {
    expect(
      canEnterStep(
        4.5,
        1,
        state({
          boxLocked: false,
          step4Ok: false,
          highestReachedStep: 5,
        }),
      ),
    ).toBe(true);
  });

  it("allows revisiting step 5 while looking at stale results", () => {
    expect(
      canEnterStep(5, 1, state({ boxLocked: false, step4Ok: true, highestReachedStep: 5 })),
    ).toBe(true);
  });
});

describe("getStepBlockReason", () => {
  it("returns reason for missing input on first visit", () => {
    expect(getStepBlockReason(2, state({ inputRows: [{ ...EMPTY_ROW }], highestReachedStep: 1 }))).toMatch(
      /第 1 步/,
    );
  });

  it("returns null when revisiting even if lock is gone", () => {
    expect(getStepBlockReason(4, state({ boxLocked: false, highestReachedStep: 4 }))).toBeNull();
  });

  it("returns null when first-visit allowed", () => {
    expect(getStepBlockReason(3, state({ highestReachedStep: 2 }))).toBeNull();
  });

  it("names step 4 when invoice is locked", () => {
    expect(getStepBlockReason(4.5, state({ step4Ok: false, highestReachedStep: 4 }))).toBe(
      "请先完成第 4 步：货件校验",
    );
  });
});

describe("inferHighestReached", () => {
  it("does not treat a saved step 5 as reached without step4Ok", () => {
    expect(
      inferHighestReached({ step: 5, boxLocked: true, step4Ok: false }),
    ).toBe(3);
  });

  it("keeps watermark when step4Ok is true", () => {
    expect(
      inferHighestReached({ step: 5, highestReachedStep: 5, boxLocked: true, step4Ok: true }),
    ).toBe(5);
  });

  it("raises to 4.5 when invoice exists", () => {
    expect(
      inferHighestReached({ step: 4, boxLocked: true, step4Ok: true, hasInvoice: true }),
    ).toBe(4.5);
  });
});
