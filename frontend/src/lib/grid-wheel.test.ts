import { describe, expect, it } from "vitest";
import { sheetScrollTop, sheetWheelMetrics, verticalWheelTarget, wheelPixelDelta, wheelTargetAfterStuck } from "@/lib/grid-wheel";

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

  it("adds the rows above the viewport to the in-row offset", () => {
    const ends = [20, 50, 90, 140];
    expect(sheetScrollTop(ends, 0, 4)).toBe(4);
    expect(sheetScrollTop(ends, 3, 2)).toBe(92);
    const metrics = sheetWheelMetrics({
      hostHeight: 80,
      rowHeights: ends,
      maxRows: 4,
      offsetY: 2,
      startRow: 3,
      columnHeaderHeight: 20,
    });
    expect(metrics.scrollOffsetY).toBe(92);
    expect(verticalWheelTarget({ ...metrics, deltaY: 30 })).toBe("sheet");
    const atEnd = sheetWheelMetrics({
      hostHeight: 80,
      rowHeights: ends,
      maxRows: 4,
      offsetY: 22,
      startRow: 3,
      columnHeaderHeight: 20,
    });
    expect(verticalWheelTarget({ ...atEnd, deltaY: 30 })).toBe("page");
  });

  it("hands the page the next wheel when the sheet did not move", () => {
    const current = { deltaY: 80, scrollOffsetY: 10, at: 100 };
    expect(wheelTargetAfterStuck("sheet", { target: "sheet", deltaY: 80, scrollOffsetY: 10, at: 40 }, current)).toBe("page");
    expect(wheelTargetAfterStuck("sheet", { target: "sheet", deltaY: 80, scrollOffsetY: 10, at: 90 }, current)).toBe("sheet");
    expect(wheelTargetAfterStuck("sheet", { target: "sheet", deltaY: 80, scrollOffsetY: 40, at: 40 }, current)).toBe("sheet");
    expect(wheelTargetAfterStuck("sheet", { target: "page", deltaY: 80, scrollOffsetY: 10, at: 40 }, current)).toBe("sheet");
    expect(verticalWheelTarget({
      measurable: false,
      scrollOffsetY: 0,
      contentHeight: 0,
      viewportHeight: 0,
      deltaY: 40,
      startRow: 0,
    })).toBe("page");
  });

  it("converts line and page wheel deltas to pixels", () => {
    expect(wheelPixelDelta(3, 1)).toBe(48);
    expect(wheelPixelDelta(1, 2, 600)).toBe(600);
    expect(wheelPixelDelta(12, 0)).toBe(12);
  });
});
