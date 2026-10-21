export interface SheetWheelMetrics {
  measurable: boolean;
  scrollOffsetY: number;
  contentHeight: number;
  viewportHeight: number;
}

export function sheetWheelMetrics(input: {
  hostHeight: number;
  rowHeights: number[] | null;
  maxRows: number;
  offsetY: number;
  columnHeaderHeight: number;
}): SheetWheelMetrics {
  const contentHeight = input.rowHeights && input.rowHeights.length
    ? input.rowHeights[input.rowHeights.length - 1]
    : Math.max(0, input.maxRows) * 24;
  const viewportHeight = Math.max(0, input.hostHeight - input.columnHeaderHeight - 32);
  return {
    measurable: input.hostHeight > 0 && contentHeight > 0,
    scrollOffsetY: input.offsetY,
    contentHeight,
    viewportHeight,
  };
}

/** 表格还能沿这个方向滚时留给表格；到头（或本来就短）时交给页面。 */
export function verticalWheelTarget(input: SheetWheelMetrics & { deltaY: number }): "sheet" | "page" {
  if (!input.measurable || input.deltaY === 0) return "sheet";
  const maxOffset = input.contentHeight - input.viewportHeight;
  if (maxOffset <= 1) return "page";
  if (input.deltaY > 0 && input.scrollOffsetY >= maxOffset - 1) return "page";
  if (input.deltaY < 0 && input.scrollOffsetY <= 1) return "page";
  return "sheet";
}

export function metricsFromUniverSheet(sheet: unknown, hostHeight: number): SheetWheelMetrics {
  const api = sheet as {
    getSkeleton?: () => { rowHeightAccumulation?: number[]; columnHeaderHeight?: number } | null | undefined;
    getScrollState?: () => { offsetY?: number } | null | undefined;
    getMaxRows?: () => number;
  } | null;
  let rowHeights: number[] | null = null;
  let columnHeaderHeight = 0;
  let offsetY = 0;
  let maxRows = 0;
  try {
    const skeleton = api?.getSkeleton?.();
    rowHeights = skeleton?.rowHeightAccumulation ?? null;
    columnHeaderHeight = skeleton?.columnHeaderHeight ?? 0;
    offsetY = api?.getScrollState?.()?.offsetY ?? 0;
    maxRows = api?.getMaxRows?.() ?? 0;
  } catch {
    rowHeights = null;
  }
  return sheetWheelMetrics({ hostHeight, rowHeights, maxRows, offsetY, columnHeaderHeight });
}

export function wheelPixelDelta(delta: number, deltaMode: number, pageSize = 800): number {
  if (deltaMode === 1) return delta * 16;
  if (deltaMode === 2) return delta * pageSize;
  return delta;
}
