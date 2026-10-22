import { describe, expect, it } from "vitest";
import {
  applyFillsToSheets,
  cellMetaFromFills,
  missingRequiredFromCellMeta,
  type Sheet,
} from "@/lib/invoice-spreadsheet";

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

  it("writes quantity as an integer and price as a number", () => {
    const template: Sheet[] = [{ name: "发票", row: 8, column: 8, celldata: [] }];
    const merged = applyFillsToSheets(template, [
      { cell: "F2", value: "4.0", field_key: "qty_per_box", source: "精准提取" },
      { cell: "G2", value: "39.99", field_key: "declared_price", source: "精准提取" },
      { cell: "L2", value: "9507100090", field_key: "hs_code", source: "精准提取" },
    ]);
    const row = merged[0]!.data![1]!;
    expect(row[5]).toMatchObject({ v: 4, m: "4" });
    expect(row[6]).toMatchObject({ v: 39.99, m: "39.99" });
    expect(row[11]).toMatchObject({ v: "9507100090", m: "9507100090" });
  });
});

describe("missingRequiredFromCellMeta", () => {
  it("names an empty required declared price on that row", () => {
    const cells = [
      { cell: "D2", value: "TANZI", field_key: "sku", source: "精准提取" },
      { cell: "G2", value: "", field_key: "declared_price", source: "必填", required: true },
      { cell: "D3", value: "OTHER", field_key: "sku", source: "精准提取" },
      { cell: "G3", value: "39.99", field_key: "declared_price", source: "精准提取", required: true },
    ];
    const labels = missingRequiredFromCellMeta(cellMetaFromFills(cells), (cell) => {
      return cell.toUpperCase() === "G3" ? "39.99" : "";
    }, cells);
    expect(labels.join(" ")).toContain("TANZI");
    expect(labels.join(" ")).toContain("申报单价 (USD)");
    expect(labels.join(" ")).not.toContain("OTHER");
  });
});
