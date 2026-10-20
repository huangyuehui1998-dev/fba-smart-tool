import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/app-shell";
import { PdfToolsWorkspace } from "@/components/pdf-tools-workspace";

export const Route = createFileRoute("/pdf-labels")({
  head: () => ({
    meta: [{ title: "PDF 标签处理 · FBA Smart Tool" }],
  }),
  component: PdfLabelsPage,
});

function PdfLabelsPage() {
  return (
    <AppShell>
      <PdfToolsWorkspace />
    </AppShell>
  );
}
