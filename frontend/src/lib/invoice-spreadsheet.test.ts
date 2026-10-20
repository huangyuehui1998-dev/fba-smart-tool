import { describe, expect, it } from "vitest";
import type { Sheet } from "@fortune-sheet/core";
import { applyFillsToSheets } from "@/lib/invoice-spreadsheet";

describe("applyFillsToSheets", () => {
  it("returns sheet with data matrix for FortuneSheet remount", () => {
    const template: Sheet[] = [
      {
        name: "发票",
        id: "sheet_0",
        status: 1,
        order: 0,
        row: 40,
        column: 20,
        celldata: [{ r: 0, c: 0, v: { v: "标题", m: "标题" } }],
        config: {},
      },
    ];

    const merged = applyFillsToSheets(template, [
      { cell: "B2", value: "SKU-1", source: "精准提取", field_key: "sku" },
    ]);

    expect(merged).toHaveLength(1);
    const sheet = merged[0]!;
    expect(Array.isArray(sheet.data)).toBe(true);
    expect(sheet.data!.length).toBeGreaterThanOrEqual(2);
    expect(sheet.data![1]![1]).toMatchObject({ v: "SKU-1", m: "SKU-1" });
    expect(sheet.celldata?.length).toBeGreaterThan(0);
    expect(sheet.calcChain).toEqual([]);
  });
});
