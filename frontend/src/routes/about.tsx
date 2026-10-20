import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { LegacyDataDialog } from "@/components/legacy-data-dialog";

export const Route = createFileRoute("/about")({
  head: () => ({
    meta: [{ title: "关于 · FBA Smart Tool" }],
  }),
  component: AboutPage,
});

interface HealthInfo {
  data_dir?: string;
  schema_version?: number;
  carton_spec_count?: number;
  version?: string;
  migration_error?: string;
  readonly?: boolean;
}

interface LegacyStatus {
  needs_import?: boolean;
  legacy_dir?: string;
  message?: string;
}

function AboutPage() {
  const [health, setHealth] = useState<HealthInfo>({});
  const [legacy, setLegacy] = useState<LegacyStatus>({});
  const [open, setOpen] = useState(false);

  useEffect(() => {
    fetch("/api/health")
      .then((response) => response.json())
      .then((body: HealthInfo) => setHealth(body))
      .catch(() => setHealth({}));
    fetch("/api/data-dir/status")
      .then((response) => response.json())
      .then((body: LegacyStatus) => {
        setLegacy(body);
        setOpen(Boolean(body.needs_import));
      })
      .catch(() => setLegacy({}));
  }, []);

  return (
    <AppShell>
      <div className="space-y-3 p-4 text-sm">
        <h1 className="text-lg font-semibold">关于</h1>
        <p>版本 {health.version ?? "—"}</p>
        <p>数据目录 {health.data_dir ?? "—"}</p>
        <p>数据库版本 {health.schema_version ?? "—"}</p>
        <p>箱规条数 {health.carton_spec_count ?? "—"}</p>
        {health.migration_error ? <p>{health.migration_error}</p> : null}
        {health.readonly ? <p>数据库版本高于当前程序，已只读打开</p> : null}
      </div>
      <LegacyDataDialog
        path={legacy.legacy_dir ?? ""}
        open={open}
        onOpenChange={setOpen}
        onConfirm={() => {
          void fetch("/api/data-dir/import-legacy", { method: "POST" }).finally(() => setOpen(false));
        }}
      />
    </AppShell>
  );
}
