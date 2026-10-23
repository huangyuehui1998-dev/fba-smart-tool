export interface SheetWheelMetrics {
  measurable: boolean;
  scrollOffsetY: number;
  contentHeight: number;
  viewportHeight: number;
  startRow: number;
}

/** Univer 的 offsetY 只是当前行内余量。累积行高才是离表格顶部的距离。 */
export function sheetScrollTop(rowEnds: number[] | null, startRow: number, offsetY: number): number {
  const row = Math.max(0, Math.floor(startRow) || 0);
  const base = row > 0 && rowEnds?.length ? rowEnds[Math.min(row - 1, rowEnds.length - 1)] ?? 0 : 0;
  return base + (Number.isFinite(offsetY) ? offsetY : 0);
}

export function sheetWheelMetrics(input: {
  hostHeight: number;
  rowHeights: number[] | null;
  maxRows: number;
  offsetY: number;
  startRow?: number;
  columnHeaderHeight: number;
}): SheetWheelMetrics {
  const contentHeight = input.rowHeights && input.rowHeights.length
    ? input.rowHeights[input.rowHeights.length - 1]
    : Math.max(0, input.maxRows) * 24;
  const viewportHeight = Math.max(0, input.hostHeight - input.columnHeaderHeight - 32);
  return {
    measurable: input.hostHeight > 0 && contentHeight > 0,
    scrollOffsetY: sheetScrollTop(input.rowHeights, input.startRow ?? 0, input.offsetY),
    contentHeight,
    viewportHeight,
    startRow: Math.max(0, Math.floor(input.startRow ?? 0) || 0),
  };
}

/** 表格还能沿这个方向滚时留给表格；到头（或本来就短）时交给页面。 */
export function verticalWheelTarget(input: SheetWheelMetrics & { deltaY: number }): "sheet" | "page" {
  if (input.deltaY === 0) return "sheet";
  if (!input.measurable) return "page";
  const maxOffset = input.contentHeight - input.viewportHeight;
  if (maxOffset <= 1) return "page";
  if (input.deltaY > 0 && input.scrollOffsetY >= maxOffset - 1) return "page";
  if (input.deltaY < 0 && input.scrollOffsetY <= 1) return "page";
  return "sheet";
}

/** 同一方向滚了一次却没移动，说明表格已经到头（或量不到），下一轮交给页面。 */
export function wheelTargetAfterStuck(
  target: "sheet" | "page",
  previous: { target: "sheet" | "page"; deltaY: number; scrollOffsetY: number; at: number } | null,
  current: { deltaY: number; scrollOffsetY: number; at: number },
): "sheet" | "page" {
  if (target !== "sheet" || previous?.target !== "sheet") return target;
  if (Math.sign(previous.deltaY) !== Math.sign(current.deltaY)) return target;
  if (current.at - previous.at < 32) return target;
  if (Math.abs(current.scrollOffsetY - previous.scrollOffsetY) > 0.5) return target;
  return "page";
}

export function metricsFromUniverSheet(sheet: unknown, hostHeight: number): SheetWheelMetrics {
  const api = sheet as {
    getSkeleton?: () => { rowHeightAccumulation?: number[]; columnHeaderHeight?: number } | null | undefined;
    getScrollState?: () => { offsetY?: number; sheetViewStartRow?: number } | null | undefined;
    getMaxRows?: () => number;
  } | null;
  let rowHeights: number[] | null = null;
  let columnHeaderHeight = 0;
  let offsetY = 0;
  let startRow = 0;
  let maxRows = 0;
  try {
    const skeleton = api?.getSkeleton?.();
    rowHeights = skeleton?.rowHeightAccumulation ?? null;
    columnHeaderHeight = skeleton?.columnHeaderHeight ?? 0;
    const scroll = api?.getScrollState?.();
    offsetY = scroll?.offsetY ?? 0;
    startRow = scroll?.sheetViewStartRow ?? 0;
    maxRows = api?.getMaxRows?.() ?? 0;
  } catch {
    rowHeights = null;
  }
  return sheetWheelMetrics({ hostHeight, rowHeights, maxRows, offsetY, startRow, columnHeaderHeight });
}

export function wheelPixelDelta(delta: number, deltaMode: number, pageSize = 800): number {
  if (deltaMode === 1) return delta * 16;
  if (deltaMode === 2) return delta * pageSize;
  return delta;
}
