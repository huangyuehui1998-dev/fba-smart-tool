import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  ABNORMAL_CLASS,
  COMPARE_COLUMNS,
  CONFIRM_NEW_SPEC_TITLE,
  PAGE_PADDING_CLASS,
  TABLE_HEAD_CLASS,
  TABLE_SCROLL_CLASS,
  compareColumns,
  dupExcludedNote,
  legacyImportMessage,
  statusClass,
} from "./carton-compare-view";
import { applyCartonSpec, type CartonSpecOption } from "./step1-carton";

describe("carton compare view", () => {
  it("keeps the published column order and duplicate note", () => {
    expect(COMPARE_COLUMNS).toEqual([
      "箱号",
      "SKU",
      "申报 L/W/H/kg",
      "实测 L/W/H/kg",
      "差值",
      "体积重差",
      "计费重差",
      "状态",
    ]);
    expect(dupExcludedNote(1)).toBe("1 个重复箱号未计入汇总");
    expect(compareColumns({})).toEqual([...COMPARE_COLUMNS]);
  });

  it("marks abnormal rows and keeps the summary strings", () => {
    expect(statusClass("异常")).toBe(ABNORMAL_CLASS);
    expect(statusClass("正常")).toBe("");
    const headline =
      "计费重总差 +320.01kg = 实重贡献 0.00 + 尺寸贡献 +318.71 + 进位 +1.30（全票口径）";
    const reference = "实重差 −28.37kg（仅参考，去重 154 箱）";
    expect(headline).toContain("+320.01kg");
    expect(reference).toContain("−28.37kg");
    expect(reference).toContain("去重 154 箱");
  });

  it("asks before importing an old data directory", () => {
    expect(legacyImportMessage("/tmp/old")).toBe("检测到旧数据目录 /tmp/old，是否导入");
  });

  it("uses a confirm dialog and a sticky scrolling table", () => {
    const source = readFileSync(new URL("../components/carton-compare-workspace.tsx", import.meta.url), "utf8");
    expect(CONFIRM_NEW_SPEC_TITLE).toBe("生成新箱规版本");
    expect(TABLE_SCROLL_CLASS).toContain("overflow-x-auto");
    expect(TABLE_HEAD_CLASS).toContain("sticky");
    expect(PAGE_PADDING_CLASS).toContain("pb-24");
    expect(source).toContain("CONFIRM_NEW_SPEC_TITLE");
    expect(source).toContain("AlertDialog");
    expect(source).not.toContain("window.confirm");
    expect(source).toContain("dup-excluded-note");
    expect(source).toContain("TABLE_SCROLL_CLASS");
    expect(source).toContain("TABLE_HEAD_CLASS");
    expect(source).toContain("PAGE_PADDING_CLASS");
  });
});

describe("step1 carton spec", () => {
  it("fills empty carton cells from the chosen spec", () => {
    const spec: CartonSpecOption = {
      id: 2,
      spec_name: "装量10",
      qty_per_carton: 10,
      length_cm: 50,
      width_cm: 30,
      height_cm: 20,
      gross_kg: 8,
      is_default: false,
    };
    const next = applyCartonSpec(
      {
        sku: "TEST_SKU",
        fnsku: "",
        totalQty: "20",
        perBox: "",
        l: "",
        w: "",
        h: "",
        unitKg: "",
        emptyKg: "",
        grossKg: "",
      },
      spec,
    );
    expect(next.perBox).toBe("10");
    expect(next.l).toBe("50");
    expect(next.w).toBe("30");
    expect(next.h).toBe("20");
    expect(next.grossKg).toBe("8");
    expect(next.totalQty).toBe("20");
  });
});
