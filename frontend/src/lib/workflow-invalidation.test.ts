import { describe, expect, it } from "vitest";

import {
  STAGE_ORDER,
  clearStageStale,
  clearStaleFrom,
  createEmptyStaleness,
  effectiveStaleness,
  getOfficialFilesForStage,
  getStaleOfficialFileLabels,
  getStaleStageLabels,
  hasAnyStale,
  invalidateFrom,
  isOfficialExportBlocked,
  isStepStale,
  parseStaleness,
  type WorkflowOutputPresence,
} from "./workflow-invalidation";

describe("createEmptyStaleness", () => {
  it("returns all stages as not stale", () => {
    const s = createEmptyStaleness();
    for (const stage of STAGE_ORDER) {
      expect(s[stage]).toBe(false);
    }
  });
});

describe("invalidateFrom", () => {
  it("marks all downstream stages stale when input changes", () => {
    const next = invalidateFrom("input");
    expect(next.input).toBe(false);
    expect(next.boxing).toBe(true);
    expect(next.export).toBe(true);
    expect(next.routing).toBe(true);
    expect(next.validation).toBe(true);
    expect(next.invoice).toBe(true);
    expect(next.customs).toBe(true);
  });

  it("marks export through customs stale when boxing changes", () => {
    const next = invalidateFrom("boxing");
    expect(next.input).toBe(false);
    expect(next.boxing).toBe(false);
    expect(next.export).toBe(true);
    expect(next.routing).toBe(true);
    expect(next.validation).toBe(true);
    expect(next.invoice).toBe(true);
    expect(next.customs).toBe(true);
  });

  it("marks routing through customs stale when export changes", () => {
    const next = invalidateFrom("export");
    expect(next.boxing).toBe(false);
    expect(next.export).toBe(false);
    expect(next.routing).toBe(true);
    expect(next.validation).toBe(true);
    expect(next.invoice).toBe(true);
    expect(next.customs).toBe(true);
  });

  it("marks only customs stale when invoice changes", () => {
    const next = invalidateFrom("invoice");
    expect(next.validation).toBe(false);
    expect(next.invoice).toBe(false);
    expect(next.customs).toBe(true);
  });

  it("does not mark anything stale when customs changes", () => {
    const next = invalidateFrom("customs");
    expect(hasAnyStale(next)).toBe(false);
  });

  it("preserves existing stale flags on unrelated upstream stages", () => {
    const current = createEmptyStaleness();
    current.routing = true;
    const next = invalidateFrom("export", current);
    expect(next.routing).toBe(true);
    expect(next.validation).toBe(true);
  });
});

describe("clearStageStale", () => {
  it("clears only the target stage without affecting downstream", () => {
    const stale = invalidateFrom("input");
    const cleared = clearStageStale("boxing", stale);
    expect(cleared.boxing).toBe(false);
    expect(cleared.export).toBe(true);
    expect(cleared.validation).toBe(true);
  });
});

describe("clearStaleFrom", () => {
  it("clears target stage and all downstream", () => {
    const stale = invalidateFrom("input");
    const cleared = clearStaleFrom("boxing", stale);
    expect(cleared.boxing).toBe(false);
    expect(cleared.export).toBe(false);
    expect(cleared.validation).toBe(false);
    expect(cleared.customs).toBe(false);
  });

  it("does not clear upstream stages", () => {
    const stale = invalidateFrom("input");
    const cleared = clearStaleFrom("validation", stale);
    expect(cleared.boxing).toBe(true);
    expect(cleared.export).toBe(true);
    expect(cleared.validation).toBe(false);
    expect(cleared.invoice).toBe(false);
  });
});

describe("hasAnyStale", () => {
  it("returns false for empty staleness", () => {
    expect(hasAnyStale(createEmptyStaleness())).toBe(false);
  });

  it("checks only specified stages when provided", () => {
    const s = invalidateFrom("export");
    expect(hasAnyStale(s, ["boxing", "export"])).toBe(false);
    expect(hasAnyStale(s, ["validation", "invoice"])).toBe(true);
  });
});

describe("getStaleStageLabels", () => {
  it("returns Chinese labels for stale stages", () => {
    const labels = getStaleStageLabels(invalidateFrom("boxing"));
    expect(labels).toContain("Step 3 导出");
    expect(labels).toContain("Step 4 回传校验");
    expect(labels).not.toContain("Step 2 排箱");
  });
});

describe("isStepStale", () => {
  it("maps UI step numbers to staleness flags", () => {
    const s = invalidateFrom("input");
    expect(isStepStale(1, s)).toBe(false);
    expect(isStepStale(2, s)).toBe(true);
    expect(isStepStale(3, s)).toBe(true);
    expect(isStepStale(3.5, s)).toBe(true);
    expect(isStepStale(4, s)).toBe(true);
    expect(isStepStale(4.5, s)).toBe(true);
    expect(isStepStale(5, s)).toBe(true);
  });
});

describe("official export blocking", () => {
  it("blocks downloads for stale stages and lists files", () => {
    const s = invalidateFrom("input");
    expect(isOfficialExportBlocked("export", s)).toBe(true);
    expect(isOfficialExportBlocked("validation", s)).toBe(true);
    expect(getOfficialFilesForStage("validation")).toContain("发货表");
    expect(getStaleOfficialFileLabels(s)).toContain("Send to Amazon 模板");
    expect(getStaleOfficialFileLabels(s)).toContain("货代发票");
  });

  it("does not block when stage is fresh", () => {
    expect(isOfficialExportBlocked("export", createEmptyStaleness())).toBe(false);
  });

  it("parses persisted staleness JSON", () => {
    const parsed = parseStaleness({ export: true, validation: "yes" });
    expect(parsed.export).toBe(true);
    expect(parsed.validation).toBe(true);
    expect(parsed.boxing).toBe(false);
  });
});

const emptyOutputs = (): WorkflowOutputPresence => ({
  boxEditorCount: 0,
  step3MatrixCount: 0,
  routingSnapshotCount: 0,
  step4Ok: false,
  step4StatusLineCount: 0,
  hasInvoiceDraft: false,
  invoiceSessionCount: 0,
  hasCustomsSession: false,
});

describe("effectiveStaleness", () => {
  it("hides stale marks when downstream stages have no output", () => {
    const raw = invalidateFrom("validation");
    const visible = effectiveStaleness(raw, emptyOutputs());
    expect(raw.invoice).toBe(true);
    expect(raw.customs).toBe(true);
    expect(visible.invoice).toBe(false);
    expect(visible.customs).toBe(false);
    expect(isStepStale(4.5, visible)).toBe(false);
    expect(isStepStale(5, visible)).toBe(false);
  });

  it("keeps the invoice stale after an upstream change once a draft exists", () => {
    const raw = invalidateFrom("input");
    const visible = effectiveStaleness(raw, {
      ...emptyOutputs(),
      hasInvoiceDraft: true,
    });
    expect(visible.invoice).toBe(true);
    expect(visible.customs).toBe(false);
  });

  it("uses saved routing snapshots, not the forwarder table, as routing output", () => {
    const raw = invalidateFrom("export");
    const withoutSnapshots = effectiveStaleness(raw, {
      ...emptyOutputs(),
      step3MatrixCount: 2,
    });
    expect(withoutSnapshots.routing).toBe(false);
    const withSnapshots = effectiveStaleness(raw, {
      ...emptyOutputs(),
      routingSnapshotCount: 1,
    });
    expect(withSnapshots.routing).toBe(true);
  });

  it("restores raw marks from a history snapshot and masks stages that were never produced", () => {
    const restored = parseStaleness({
      boxing: true,
      export: true,
      routing: true,
      validation: true,
      invoice: true,
      customs: true,
    });
    const visible = effectiveStaleness(restored, {
      ...emptyOutputs(),
      boxEditorCount: 4,
      step4Ok: true,
      invoiceSessionCount: 1,
    });
    expect(visible.boxing).toBe(true);
    expect(visible.export).toBe(false);
    expect(visible.routing).toBe(false);
    expect(visible.validation).toBe(true);
    expect(visible.invoice).toBe(true);
    expect(visible.customs).toBe(false);
  });
});
