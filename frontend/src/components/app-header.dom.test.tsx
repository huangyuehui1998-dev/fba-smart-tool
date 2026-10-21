// @vitest-environment happy-dom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { AppHeader } from "@/components/app-header";
import { EMPTY_ROW } from "@/lib/step1-rows";
import { WORKFLOW_STEPS } from "@/lib/workflow-steps";

describe("step nav", () => {
  it("numbers steps 1 through 7 and explains a locked step 5", async () => {
    const user = userEvent.setup();
    render(
      <AppHeader
        currentStep={3}
        stepGuard={{
          inputRows: [{ ...EMPTY_ROW, sku: "TEST_A", totalQty: "4" }],
          boxLocked: true,
          boxEditorApi: [{ 箱号: 1, 来源: "整箱", SKU简称: "TEST_A", 数量: 4 }],
          step4Ok: false,
          highestReachedStep: 3,
        }}
      />,
    );

    const labels = WORKFLOW_STEPS.map((step) => step.label);
    expect(labels.map((label) => label[0])).toEqual(["1", "2", "3", "4", "5", "6", "7"]);
    for (const label of labels) {
      expect(screen.getByRole("button", { name: label })).toBeTruthy();
    }

    await user.click(screen.getByRole("button", { name: "5 发票" }));
    expect(screen.getByRole("alertdialog").textContent).toContain("请先完成第 4 步：货件校验");
  });
});
