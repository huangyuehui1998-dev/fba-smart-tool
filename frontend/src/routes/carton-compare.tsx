import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { driver } from "driver.js";
import "driver.js/dist/driver.css";

import { AppShell } from "@/components/app-shell";
import { CARTON_TOUR_BUTTONS } from "@/lib/carton-tour";
import { BackToWorkflow } from "@/components/back-to-workflow";
import { CartonCompareWorkspace } from "@/components/carton-compare-workspace";
import { CartonSpecWizard } from "@/components/carton-spec-wizard";
import type { CompareReport } from "@/lib/carton-compare-view";

export const Route = createFileRoute("/carton-compare")({
  head: () => ({
    meta: [{ title: "箱规对比 · FBA Smart Tool" }],
  }),
  component: CartonComparePage,
});

function CartonComparePage() {
  const [report, setReport] = useState<CompareReport>({ columns: [], rows: [], quality: [] });
  const [error, setError] = useState("");

  useEffect(() => {
    if (window.localStorage.getItem("fba_carton_wizard_seen") === "1") return;
    const tour = driver({
      showProgress: true,
      ...CARTON_TOUR_BUTTONS,
      steps: [
        {
          element: "[data-testid=carton-wizard-open]",
          popover: { title: "录入箱规", description: "按四步填写 SKU、外箱尺寸、数量和重量。" },
        },
        {
          element: "[data-testid=back-to-workflow]",
          popover: { title: "返回工作流", description: "回到进入箱规页之前的步骤。" },
        },
      ],
      onDestroyed: () => window.localStorage.setItem("fba_carton_wizard_seen", "1"),
    });
    const timer = window.setTimeout(() => tour.drive(), 300);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const query = new URLSearchParams();
    for (const key of ["fba_id", "batch", "source"]) {
      const value = params.get(key);
      if (value) query.set(key, value);
    }
    fetch(`/api/carton-compare?${query.toString()}`)
      .then(async (response) => {
        if (!response.ok) throw new Error(await response.text());
        return response.json() as Promise<CompareReport>;
      })
      .then(setReport)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "对比加载失败"));
  }, []);

  return (
    <AppShell>
      <div className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-lg font-semibold">发货 / 实测箱规对比</h1>
          <div className="flex gap-2">
            <CartonSpecWizard />
            <BackToWorkflow />
          </div>
        </div>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <CartonCompareWorkspace report={report} />
      </div>
    </AppShell>
  );
}
