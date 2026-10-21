import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

interface ImportPreview {
  run_id: number;
  row_count: number;
  export_at?: string;
  anomalies?: { row?: number; sku?: string; message?: string }[];
  warnings?: string[];
  columns?: string[];
  mapping?: Record<string, string>;
  wrote_product_master?: boolean;
}

interface PreviewField {
  field: string;
  label?: string;
  default_checked?: boolean;
  locked?: boolean;
}

interface PreviewSku {
  sku: string;
  fields?: PreviewField[];
}

export function LingxingXlsxImport({ onImported }: { onImported?: () => void }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [busy, setBusy] = useState(false);

  const upload = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/lingxing/import-xlsx", { method: "POST", body });
      if (!response.ok) throw new Error(await response.text());
      const payload = (await response.json()) as ImportPreview;
      if (payload.wrote_product_master) throw new Error("预览阶段不应写入产品库");
      setPreview(payload);
      toast.success(`已生成预览，${payload.row_count} 行，尚未写入`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "导入失败");
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!preview) return;
    setBusy(true);
    try {
      const response = await fetch(`/api/lingxing/sync/preview?run_id=${preview.run_id}`);
      if (!response.ok) throw new Error(await response.text());
      const payload = (await response.json()) as { groups?: Record<string, PreviewSku[]> };
      const items = Object.values(payload.groups || {}).flatMap((rows) =>
        rows
          .map((row) => ({
            sku: row.sku,
            fields: (row.fields || []).filter((field) => field.default_checked && !field.locked).map((field) => field.field),
          }))
          .filter((row) => row.fields.length > 0),
      );
      const saved = await fetch("/api/lingxing/sync/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ run_id: preview.run_id, items }),
      });
      if (!saved.ok) throw new Error(await saved.text());
      toast.success("已按预览确认写入");
      setOpen(false);
      onImported?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "确认失败");
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <Button type="button" size="sm" variant="outline" data-testid="lingxing-xlsx-open" onClick={() => setOpen(true)}>
        导入领星表格
      </Button>
    );
  }

  return (
    <div className="w-full basis-full space-y-2 rounded-lg border border-border p-3 text-sm" data-testid="lingxing-xlsx-import">
      <p className="font-medium">领星网页导出 · 预览后确认</p>
      <input
        data-testid="lingxing-xlsx-file"
        type="file"
        accept=".xlsx"
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
      />
      <div className="flex flex-wrap gap-2">
        <Button type="button" size="sm" data-testid="lingxing-xlsx-preview" disabled={!file || busy} onClick={() => void upload()}>
          生成预览
        </Button>
        <Button type="button" size="sm" data-testid="lingxing-xlsx-confirm" disabled={!preview || busy} onClick={() => void confirm()}>
          确认写入
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
          关闭
        </Button>
      </div>
      {preview && (
        <div className="space-y-1 text-xs text-muted-foreground" data-testid="lingxing-xlsx-summary">
          <p>
            {preview.row_count} 行可导入
            {preview.export_at ? ` · 导出日期 ${preview.export_at}` : ""}
            {preview.wrote_product_master ? " · 已写库" : " · 尚未写库"}
          </p>
          <p>列映射：{Object.entries(preview.mapping || {}).slice(0, 8).map(([header, field]) => `${header}→${field}`).join("，")}</p>
          {(preview.warnings || []).map((item) => (
            <p key={item}>{item}</p>
          ))}
          {(preview.anomalies || []).slice(0, 8).map((item) => (
            <p key={`${item.row}-${item.sku}`} className="text-amber-700">
              第 {item.row} 行 {item.sku}：{item.message}
            </p>
          ))}
          <a className="underline" href={`/api/lingxing/runs/${preview.run_id}/errors.csv`}>
            下载失败行
          </a>
        </div>
      )}
    </div>
  );
}
