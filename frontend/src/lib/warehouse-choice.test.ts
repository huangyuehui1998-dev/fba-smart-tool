import { describe, expect, it } from "vitest";

import { applyWarehouseChoice } from "@/lib/warehouse-choice";

describe("applyWarehouseChoice", () => {
  it("switches the forwarder warehouse code to the PDF code", () => {
    const rows = [{ 仓库代码: "CLT2", SKU: "TEST_A" }];
    const next = applyWarehouseChoice(
      rows,
      { shipment_id: "FBATEST00001", csv_code: "CLT2", pdf_code: "LAS1" },
      "pdf",
    );
    expect(next[0]?.["仓库代码"]).toBe("LAS1");
    expect(next[0]?._warehouse_choice).toBe("pdf");
  });
});
