import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/app-shell";
import { MasterDataWorkspace } from "@/components/master-data-workspace";

export const Route = createFileRoute("/master-data")({
  head: () => ({
    meta: [{ title: "产品主数据库 · FBA Smart Tool" }],
  }),
  component: MasterDataPage,
});

function MasterDataPage() {
  return (
    <AppShell>
      <MasterDataWorkspace />
    </AppShell>
  );
}
