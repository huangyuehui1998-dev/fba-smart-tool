// @vitest-environment happy-dom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CartonCompareWorkspace } from "@/components/carton-compare-workspace";

const WARNING = "与货代账单不一致，待确认";

afterEach(() => cleanup());

describe("carton compare bill warnings (G3)", () => {
  it("renders bill_warnings as an amber banner and still shows the table", () => {
    render(
      <CartonCompareWorkspace
        report={{
          columns: ["箱号", "计费重差"],
          rows: [{ 箱号: "FBATESTU000001", 计费重差: "0.00" }],
          summary: {
            headline: "计费重总差 +1.00kg = 实重贡献 0.00 + 尺寸贡献 0.00 + 进位 +1.00（全票口径）",
          },
          bill_warnings: [WARNING],
        }}
      />,
    );
    const banner = screen.getByTestId("bill-warnings");
    expect(banner.textContent).toContain(WARNING);
    expect(banner.className).toContain("text-amber-700");
    expect(banner.className).toContain("border-amber-300");
    expect(screen.getByText("FBATESTU000001")).toBeTruthy();
    expect(screen.getByText(/进位 \+1\.00/)).toBeTruthy();
  });

  it("hides the banner when bill_warnings is empty", () => {
    render(<CartonCompareWorkspace report={{ columns: ["箱号"], rows: [], bill_warnings: [] }} />);
    expect(screen.queryByTestId("bill-warnings")).toBeNull();
  });
});
