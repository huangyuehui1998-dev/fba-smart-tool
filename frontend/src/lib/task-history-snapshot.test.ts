import { describe, expect, it } from "vitest";

import { applyTaskHistorySnapshot } from "./task-history-snapshot";
import { createEmptyStaleness, invalidateFrom } from "./workflow-invalidation";

describe("applyTaskHistorySnapshot", () => {
  it("restores highest reached step and staleness", () => {
    const stale = invalidateFrom("input", createEmptyStaleness());
    const applied = applyTaskHistorySnapshot({
      task_id: "t-stale",
      task_name: "StaleTask",
      step: 5,
      box_locked: true,
      step4_validated: true,
      input_df: [{ SKU简称: "A", 发货总数: 10 }],
      box_editor_df: [{ 箱号: 1, 来源: "整箱", SKU简称: "A", 数量: 10 }],
      react_highest_reached_step: 5,
      react_staleness: stale,
    });
    expect(applied.highestReachedStep).toBe(5);
    expect(applied.staleness.validation).toBe(true);
    expect(applied.staleness.invoice).toBe(true);
    expect(applied.step4Ok).toBe(true);
  });

  it("does not invent step 5 from a locked plan alone", () => {
    const applied = applyTaskHistorySnapshot({
      task_id: "t-lock",
      step: 5,
      box_locked: true,
      step4_validated: false,
      input_df: [{ SKU简称: "A", 发货总数: 10 }],
      box_editor_df: [{ 箱号: 1, 来源: "整箱", SKU简称: "A", 数量: 10 }],
    });
    expect(applied.highestReachedStep).toBe(3);
  });
});
