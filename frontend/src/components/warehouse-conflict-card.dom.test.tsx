// @vitest-environment happy-dom
import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { WarehouseConflictCards } from "@/components/warehouse-conflict-card";

function Harness() {
  const [rows, setRows] = useState<Record<string, unknown>[]>([{ 仓库代码: "CLT2", SKU: "TEST_A" }]);
  return (
    <div>
      <WarehouseConflictCards
        warnings={[{ shipment_id: "FBATEST00001", csv_code: "CLT2", pdf_code: "LAS1" }]}
        rows={rows}
        onRows={setRows}
      />
      <output data-testid="wh">{String(rows[0]?.["仓库代码"] ?? "")}</output>
    </div>
  );
}

describe("WarehouseConflictCards", () => {
  it("shows one card and applies the PDF code", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.getAllByTestId("warehouse-warning-card")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "采用 PDF" }));
    expect(screen.getByTestId("wh").textContent).toBe("LAS1");
  });
});
