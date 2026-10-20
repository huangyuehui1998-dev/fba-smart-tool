import type { Image, Sheet } from "@fortune-sheet/core";

type FortuneImageRecord = Record<
  string,
  {
    src?: string;
    id?: string;
    left?: number;
    top?: number;
    width?: number;
    height?: number;
    originWidth?: number;
    originHeight?: number;
    default?: { left?: number; top?: number; width?: number; height?: number };
  }
>;

/** fortune-excel 导出 images 为对象，FortuneSheet 需要 Image[] */
export function normalizeSheetImages(images: unknown): Image[] {
  if (!images) return [];
  if (Array.isArray(images)) {
    return images
      .filter((img) => img && typeof img === "object")
      .map((img, index) => {
        const row = img as Image;
        return {
          id: row.id || `image_${index}`,
          src: String(row.src ?? ""),
          left: Number(row.left ?? 0),
          top: Number(row.top ?? 0),
          width: Number(row.width ?? 0),
          height: Number(row.height ?? 0),
        };
      })
      .filter((img) => img.src);
  }
  if (typeof images === "object") {
    return Object.entries(images as FortuneImageRecord)
      .map(([key, img]) => {
        const box = img.default ?? img;
        return {
          id: img.id || key,
          src: String(img.src ?? ""),
          left: Number(box.left ?? 0),
          top: Number(box.top ?? 0),
          width: Number(box.width ?? img.originWidth ?? 0),
          height: Number(box.height ?? img.originHeight ?? 0),
        };
      })
      .filter((img) => img.src);
  }
  return [];
}

function normalizeCelldata(celldata: unknown): Sheet["celldata"] | undefined {
  if (!Array.isArray(celldata)) return undefined;

  const normalized = celldata
    .map((cell) => {
      if (!cell || typeof cell !== "object") return null;
      const row = cell as { r?: unknown; c?: unknown; v?: unknown };
      const r = Number(row.r);
      const c = Number(row.c);
      if (!Number.isFinite(r) || !Number.isFinite(c) || row.v == null) return null;
      return { ...cell, r, c };
    })
    .filter(Boolean) as NonNullable<Sheet["celldata"]>;

  if (normalized.length > 0) return normalized;
  return celldata as Sheet["celldata"];
}

/** 规范化 fortune-excel 输出，避免 Workbook 初始化时因缺字段崩溃 */
export function normalizeFortuneSheets(sheets: Sheet[]): Sheet[] {
  if (!Array.isArray(sheets) || !sheets.length) {
    return [
      {
        name: "Sheet1",
        id: "sheet_0",
        status: 1,
        order: 0,
        row: 84,
        column: 60,
        celldata: [],
        config: {},
        images: [],
      },
    ];
  }

  return sheets.map((sheet, index) => {
    const row = Math.max(Number(sheet.row) || 0, 36);
    const column = Math.max(Number(sheet.column) || 0, 18);
    const celldata = normalizeCelldata(sheet.celldata);

    return {
      ...sheet,
      name: sheet.name || `Sheet${index + 1}`,
      id: sheet.id || `sheet_${index}`,
      index: (sheet as { index?: string | number }).index ?? String(index),
      status: index === 0 ? 1 : sheet.status ?? 0,
      order: sheet.order ?? index,
      row,
      column,
      showGridLines: sheet.showGridLines ?? 1,
      ...(celldata ? { celldata } : {}),
      config: sheet.config ?? {},
      images: normalizeSheetImages(sheet.images),
      calcChain: Array.isArray(sheet.calcChain) ? sheet.calcChain : [],
      luckysheet_select_save: Array.isArray(sheet.luckysheet_select_save)
        ? sheet.luckysheet_select_save
        : [{ row: [0, 0], column: [0, 0] }],
    };
  });
}

export function createEmptyFortuneSheet(): Sheet[] {
  return normalizeFortuneSheets([]);
}

export function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof document !== "undefined";
}
