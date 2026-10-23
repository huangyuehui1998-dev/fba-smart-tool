import { describe, expect, it } from "vitest";
import { FILL_FAILED_EXPORT_BLOCK, exportBlockAfterFailedFill } from "@/lib/invoice-export-guard";

describe("export after failed auto-fill", () => {
  it("blocks the empty template and says why", () => {
    expect(exportBlockAfterFailedFill(true)).toBe(FILL_FAILED_EXPORT_BLOCK);
    expect(FILL_FAILED_EXPORT_BLOCK).toContain("已阻止导出");
  });

  it("allows export when the last auto-fill did not fail", () => {
    expect(exportBlockAfterFailedFill(false)).toBeNull();
  });
});
