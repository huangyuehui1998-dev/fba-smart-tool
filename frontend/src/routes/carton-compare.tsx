import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { CartonCompareWorkspace } from "@/components/carton-compare-workspace";
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
        <h1 className="text-lg font-semibold">发货 / 实测箱规对比</h1>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        <CartonCompareWorkspace report={report} />
      </div>
    </AppShell>
  );
}
