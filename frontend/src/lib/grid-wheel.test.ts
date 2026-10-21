import { describe, expect, it } from "vitest";
import { sheetWheelMetrics, verticalWheelTarget, wheelPixelDelta } from "@/lib/grid-wheel";

describe("grid wheel handoff", () => {
  it("hands a short sheet to the page", () => {
    const metrics = sheetWheelMetrics({
      hostHeight: 800,
      rowHeights: [24, 48, 72, 120],
      maxRows: 4,
      offsetY: 0,
      columnHeaderHeight: 20,
    });
    expect(verticalWheelTarget({ ...metrics, deltaY: 400 })).toBe("page");
    expect(verticalWheelTarget({ ...metrics, deltaY: -100 })).toBe("page");
  });

  it("keeps the wheel in a tall sheet until the edge", () => {
    const metrics = sheetWheelMetrics({
      hostHeight: 200,
      rowHeights: null,
      maxRows: 40,
      offsetY: 0,
      columnHeaderHeight: 20,
    });
    expect(metrics.contentHeight).toBe(960);
    expect(verticalWheelTarget({ ...metrics, deltaY: 80 })).toBe("sheet");
    const atBottom = { ...metrics, scrollOffsetY: metrics.contentHeight - metrics.viewportHeight };
    expect(verticalWheelTarget({ ...atBottom, deltaY: 80 })).toBe("page");
    expect(verticalWheelTarget({ ...metrics, deltaY: -40 })).toBe("page");
  });

  it("converts line and page wheel deltas to pixels", () => {
    expect(wheelPixelDelta(3, 1)).toBe(48);
    expect(wheelPixelDelta(1, 2, 600)).toBe(600);
    expect(wheelPixelDelta(12, 0)).toBe(12);
  });
});
