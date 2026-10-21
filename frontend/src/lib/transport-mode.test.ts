import { describe, expect, it } from "vitest";

import { applyTaskHistorySnapshot, buildTaskHistorySnapshot } from "./task-history-snapshot";
import { DEFAULT_TRANSPORT_MODE, normalizeTransportMode } from "./transport-mode";
import { createEmptyStaleness } from "./workflow-invalidation";

describe("transport mode", () => {
  it("defaults unknown values to SPD partnered", () => {
    expect(normalizeTransportMode(undefined)).toBe("spd_partnered");
    expect(normalizeTransportMode("LTL-FTL")).toBe("ltl");
    expect(normalizeTransportMode("spd_own")).toBe("spd_own");
  });

  it("round-trips through the task snapshot", () => {
    const built = buildTaskHistorySnapshot({
      taskId: "t1",
      taskName: "T",
      step: 3,
      inputRows: [],
      fnskuOverrides: {},
      boxEditorApi: [],
      boxLocked: true,
      throwRatio: 5000,
      step3Matrix: [],
      step3BoxCount: 0,
      step3SkuCount: 0,
      metrics: [],
      tailPool: [],
      hasOverweight: false,
      step4Ok: false,
      step4StatusLines: [],
      step4Errors: [],
      workerPackingPreview: [],
      workerPackingWarehouses: [],
      shippingSheet: [],
      shippingSheetLegend: [],
      forwarder: [],
      shipments: [],
      actualPlacementFee: null,
      selectedShipmentId: "",
      invoiceDraft: null,
      invoiceTemplateBase64: null,
      invoiceSessionsByShipment: {},
      invoiceForwarderId: "",
      invoicePoByShipment: {},
      invoiceSyncLinkedEdits: true,
      customsSession: null,
      highestReachedStep: 3,
      staleness: createEmptyStaleness(),
      transportMode: "ltl",
    });
    expect(built.react_transport_mode).toBe("ltl");
    const applied = applyTaskHistorySnapshot(built as unknown as Record<string, unknown>);
    expect(applied.transportMode).toBe("ltl");
  });

  it("fills the default when an older snapshot has no mode", () => {
    const applied = applyTaskHistorySnapshot({ task_id: "old", step: 1 });
    expect(applied.transportMode).toBe(DEFAULT_TRANSPORT_MODE);
  });
});
