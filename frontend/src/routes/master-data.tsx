import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/app-shell";
import { MasterDataWorkspace } from "@/components/master-data-workspace";

type MasterDataSearch = {
  import?: "product-info";
};

export const Route = createFileRoute("/master-data")({
  validateSearch: (search: Record<string, unknown>): MasterDataSearch => {
    if (search.import === "product-info") return { import: "product-info" };
    return {};
  },
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
