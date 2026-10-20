import { useCallback, useEffect, useState } from "react";
import { Database, FileSpreadsheet, Loader2, RefreshCw, Upload, ArrowLeft, CloudDownload } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api/client";
import { formatApiError } from "@/lib/format-api-error";
import {
  applyTicketImport,
  previewTicketImport,
  applyWarehouseImport,
  applyProductEdits,
  exportMasterProducts,
  previewProductEdits,
  previewWarehouseImport,
  fetchMasterDataList,
  openLocalMasterExcel,
  syncLocalMasterExcel,
  uploadMasterProductInfo,
  uploadMasterReport,
  type MasterProduct,
} from "@/lib/api/master-data";
import {
  confirmLingxingPreview,
  fetchLingxingLastRun,
  syncLingxingWithProgress,
  type LingxingPreviewPayload,
  type LingxingStockAlert,
  type LingxingSyncDiff,
} from "@/lib/api/lingxing";
import { MasterDataEditableTable } from "@/components/master-data-editable-table";
import { LingxingPreviewPanel } from "@/components/lingxing-preview-panel";
import { LingxingSchedulePanel } from "@/components/lingxing-schedule-panel";
import { DIFF_LABEL, diffItemClass } from "@/lib/diff-kinds";
import { usePreventBrowserFileDrop, fileDropZoneProps } from "@/hooks/use-prevent-browser-file-drop";

function masterDataApiError(err: unknown): string {
  if (err instanceof ApiError && err.status === 404) {
    return "主数据库接口未就绪（404）。请重启后端并确认 API 服务已启动。";
  }
  return formatApiError(err);
}

function ReportDropzone({
  title,
  hint,
  accept,
  loading,
  onFile,
}: {
  title: string;
  hint: string;
  accept: string;
  loading: boolean;
  onFile: (file: File) => void;
}) {
  const [dragOver, setDragOver] = useState(false);
  const inputId = `master-${title.replace(/\s/g, "-")}`;

  const preventDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  return (
    <div
      {...fileDropZoneProps}
      className="space-y-2"
      onDragEnter={(e) => {
        preventDrag(e);
        setDragOver(true);
      }}
      onDragLeave={(e) => {
        preventDrag(e);
        if (e.currentTarget.contains(e.relatedTarget as Node)) return;
        setDragOver(false);
      }}
      onDragOver={(e) => {
        preventDrag(e);
        e.dataTransfer.dropEffect = "copy";
        setDragOver(true);
      }}
      onDrop={(e) => {
        preventDrag(e);
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
    >
      <div
        className={cn(
          "relative rounded-lg border-2 border-dashed transition-colors",
          dragOver ? "border-primary bg-primary/10" : "border-border bg-muted/30",
        )}
      >
        <label
          htmlFor={inputId}
          className="flex cursor-pointer flex-col items-center gap-2 px-4 py-6 text-center"
        >
          {loading ? (
            <Loader2 className="h-7 w-7 animate-spin text-primary" />
          ) : (
            <Upload className="h-7 w-7 text-muted-foreground" />
          )}
          <span className="text-sm font-medium">{title}</span>
          <span className="text-xs text-muted-foreground">{hint}</span>
        </label>
      </div>
      <input
        id={inputId}
        type="file"
        accept={accept}
        className="sr-only"
        disabled={loading}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
    </div>
  );
}

type UploadKind = "fee_preview" | "inventory" | "product_info";

export function MasterDataWorkspace() {
  const [items, setItems] = useState<MasterProduct[]>([]);
  const [skuConflicts, setSkuConflicts] = useState<string[][]>([]);
  const [onlyMissingCustoms, setOnlyMissingCustoms] = useState(false);
  const missingCustomsCount = items.filter((i) => i.customs_config_status).length;
  const shownItems = onlyMissingCustoms ? items.filter((i) => i.customs_config_status) : items;
  const [loading, setLoading] = useState(true);
  const [listLoaded, setListLoaded] = useState(false);
  const [uploading, setUploading] = useState<UploadKind | null>(null);
  const [excelOpening, setExcelOpening] = useState(false);
  const [excelSyncing, setExcelSyncing] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);
  const [lxSyncing, setLxSyncing] = useState(false);
  const [lxPercent, setLxPercent] = useState(0);
  const [lxMessage, setLxMessage] = useState("");
  const [lxLastSynced, setLxLastSynced] = useState<string | null>(null);
  const [lxAlerts, setLxAlerts] = useState<LingxingStockAlert[]>([]);
  const [lxDiffs, setLxDiffs] = useState<LingxingSyncDiff[]>([]);
  const [showDiffs, setShowDiffs] = useState(false);
  const [lxPreview, setLxPreview] = useState<LingxingPreviewPayload | null>(null);
  const [lxConfirming, setLxConfirming] = useState(false);

  usePreventBrowserFileDrop();

  const loadList = useCallback(async () => {
    setLoading(true);
    setBootError(null);
    try {
      const res = await fetchMasterDataList();
      setItems(res.items);
      setSkuConflicts(res.sku_case_conflicts ?? []);
      setListLoaded(true);
    } catch (err) {
      const msg = masterDataApiError(err);
      setBootError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadLingxingMeta = useCallback(async () => {
    try {
      const res = await fetchLingxingLastRun();
      const finished = res.run && typeof res.run.finished_at === "string" ? res.run.finished_at : null;
      setLxLastSynced(finished);
      setLxAlerts(res.alerts ?? []);
      setLxDiffs(res.diffs ?? []);
      setLxPreview(res.preview?.pending ? res.preview : null);
    } catch {
      // 后端未升级时忽略
    }
  }, []);

  useEffect(() => {
    void loadList();
    void loadLingxingMeta();
  }, [loadList, loadLingxingMeta]);

  const handleAmazonUpload = async (file: File, reportType: "fee_preview" | "inventory") => {
    setUploading(reportType);
    try {
      const res = await uploadMasterReport(file, reportType);
      toast.success(
        `已解析 ${res.parsed} 条，写入/更新 ${res.upserted} 条 SKU（库中共 ${res.total_in_db} 条）`,
      );
      await loadList();
    } catch (err) {
      toast.error(masterDataApiError(err));
    } finally {
      setUploading(null);
    }
  };

  const handleProductInfoUpload = async (file: File) => {
    setUploading("product_info");
    try {
      const res = await uploadMasterProductInfo(file);
      toast.success(
        `产品信息表：解析 ${res.parsed} 条，更新 ${res.upserted} 条（库中共 ${res.total_in_db} 条）`,
      );
      await loadList();
    } catch (err) {
      toast.error(masterDataApiError(err));
    } finally {
      setUploading(null);
    }
  };

  const handleOpenLocalExcel = async () => {
    setExcelOpening(true);
    try {
      const res = await openLocalMasterExcel();
      toast.success(res.message || `已导出 ${res.rows} 条并打开 Excel`);
    } catch (err) {
      toast.error(masterDataApiError(err));
    } finally {
      setExcelOpening(false);
    }
  };

  const handleSyncLocalExcel = async () => {
    setExcelSyncing(true);
    try {
      const res = await syncLocalMasterExcel();
      toast.success(`同步成功，已更新 ${res.upserted} 条数据`);
      await loadList();
    } catch (err) {
      toast.error(masterDataApiError(err));
    } finally {
      setExcelSyncing(false);
    }
  };

  const handleRowUpdated = useCallback((row: MasterProduct) => {
    setItems((prev) => prev.map((item) => (item.sku === row.sku ? row : item)));
  }, []);

  const handleRowDeleted = useCallback((sku: string) => {
    setItems((prev) => prev.filter((item) => item.sku !== sku));
  }, []);

  const handleLingxingSync = async () => {
    setLxSyncing(true);
    setLxPercent(1);
    setLxMessage("正在连接领星 MCP…");
    setShowDiffs(false);
    setLxPreview(null);
    try {
      const result = await syncLingxingWithProgress((percent, message) => {
        setLxPercent(percent);
        setLxMessage(message);
      });
      const listing = result.counts?.listing ?? 0;
      const stock = result.counts?.fba_stock ?? 0;
      toast.success(`领星已拉取：Listing ${listing} 条，FBA 库存 ${stock} 行。主表需预览确认后才写入。`);
      if (result.preview?.pending) {
        setLxPreview(result.preview);
      }
      if (result.diffs?.length) {
        setLxDiffs(result.diffs);
        setShowDiffs(true);
        toast.message(`有 ${result.diffs.length} 条同步差异，可展开查看`);
      } else {
        setLxDiffs([]);
      }
      await loadLingxingMeta();
    } catch (err) {
      const msg = masterDataApiError(err);
      setLxMessage(msg);
      setLxPercent(0);
      toast.error(msg);
      await loadLingxingMeta();
    } finally {
      setLxSyncing(false);
    }
  };

  const handleLingxingConfirm = async (items: { sku: string; fields: string[] }[]) => {
    if (!lxPreview?.run_id) return;
    setLxConfirming(true);
    try {
      const res = await confirmLingxingPreview(lxPreview.run_id, items);
      toast.success(`已写入主库：${res.skus_patched} 个 SKU、${res.fields_written} 个字段`);
      setLxPreview(null);
      setLxMessage("");
      setLxPercent(0);
      await loadList();
      await loadLingxingMeta();
    } catch (err) {
      toast.error(masterDataApiError(err));
    } finally {
      setLxConfirming(false);
    }
  };

  return (
    <div className="flex h-[calc(100dvh-5.5rem)] min-h-0 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-lg font-semibold">
            <Database className="h-5 w-5 text-primary" />
            产品主数据库
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            SQLite 单一数据源：网页小改 · 本地 Excel 批量改 · 上传报告自动入库
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" className="gap-1.5" asChild>
            <Link to="/">
              <ArrowLeft className="h-4 w-4" />
              返回工作流
            </Link>
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => void loadList()} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            刷新列表
          </Button>
        </div>
      </div>
      {skuConflicts.length > 0 && (
        <p
          className="shrink-0 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-100"
          data-testid="sku-case-conflicts"
        >
          产品库里有只差大小写/全角半角的 SKU（亚马逊 SKU 区分大小写，系统不会自动合并）：
          {skuConflicts.map((g) => g.join(" / ")).join("；")}。匹配到这些 SKU 时不会任选一条，请确认后改名或删除多余的一条。
        </p>
      )}

      {bootError && (
        <Alert variant="destructive" className="shrink-0">
          <AlertDescription>{bootError}</AlertDescription>
        </Alert>
      )}

      {lxPreview?.pending && (
        <Alert className="shrink-0">
          <AlertDescription>库存/补货已更新，产品主表待确认。未勾选的字段不会写入。</AlertDescription>
        </Alert>
      )}

      {lxAlerts.length > 0 && (
        <Alert className="shrink-0">
          <AlertDescription>
            {lxAlerts.length} 个 SKU 可能断货
            {lxAlerts.slice(0, 3).map((a) => ` · ${a.sku || a.asin}（${a.message}）`).join("")}
            {lxAlerts.length > 3 ? "…" : ""}
          </AlertDescription>
        </Alert>
      )}

      <Card className="shrink-0">
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 pb-3">
          <div>
            <CardTitle className="text-sm">领星 ERP 一键同步</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              从领星拉取 Listing / FBA 库存 / 补货建议 / 近 30 天表现。Listing 先预览再写入主表；箱规与报关字段不会被覆盖。
              {lxLastSynced
                ? ` 上次完成：${new Date(lxLastSynced).toLocaleString()}`
                : " 尚未同步"}
            </p>
          </div>
          <Button
            size="sm"
            className="gap-1.5"
            onClick={() => void handleLingxingSync()}
            disabled={lxSyncing || loading}
          >
            {lxSyncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
            {lxSyncing ? "同步中…" : "一键同步领星"}
          </Button>
        </CardHeader>
        {(lxSyncing || lxMessage || lxPreview?.pending) && (
          <CardContent className="space-y-2 pt-0">
            {(lxSyncing || lxMessage) && (
              <>
                <Progress value={lxPercent} />
                <p className="text-xs text-muted-foreground">
                  {lxSyncing ? `正在同步：${lxMessage}` : lxMessage}（{lxPercent}%）
                </p>
              </>
            )}
            {showDiffs && lxDiffs.length > 0 && (
              <details className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs">
                <summary className="cursor-pointer font-medium">同步差异 {lxDiffs.length} 条</summary>
                <ul className="mt-2 max-h-40 space-y-1 overflow-auto text-muted-foreground">
                  {lxDiffs.map((d, i) => (
                    <li key={`${d.sku}-${i}`} className={diffItemClass(d.kind)}>
                      {DIFF_LABEL[d.kind] || d.kind}
                      {d.sku ? ` / ${d.sku}` : ""}：{d.message}
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <LingxingSchedulePanel />
            {lxPreview?.pending && (
              <LingxingPreviewPanel
                preview={lxPreview}
                confirming={lxConfirming}
                onConfirm={(items) => void handleLingxingConfirm(items)}
                onPriceConfirmed={() => void loadLingxingMeta()}
              />
            )}
          </CardContent>
        )}
      </Card>

      <div className="grid shrink-0 grid-cols-1 gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">费用预览报告 (Fee Preview)</CardTitle>
          </CardHeader>
          <CardContent>
            <ReportDropzone
              title="上传 Fee Preview CSV/TXT"
              hint="写入单品长宽高/重量 → 配置费预估（不覆盖外箱）"
              accept=".csv,.txt,.tsv,.xlsx,.xls,.xlsm,.xlsb"
              loading={uploading === "fee_preview"}
              onFile={(f) => void handleAmazonUpload(f, "fee_preview")}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">库存报告 (Active / All Listings)</CardTitle>
          </CardHeader>
          <CardContent>
            <ReportDropzone
              title="上传 Inventory Report CSV/TXT"
              hint="仅补充 ASIN / FNSKU（不解析尺寸）"
              accept=".csv,.txt,.tsv,.xlsx,.xls,.xlsm,.xlsb"
              loading={uploading === "inventory"}
              onFile={(f) => void handleAmazonUpload(f, "inventory")}
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm">产品信息总表（报关字段）</CardTitle>
          </CardHeader>
          <CardContent>
            <ReportDropzone
              title="上传产品信息 Excel / CSV"
              hint="正则解析报关名、型号名、海关编码等"
              accept=".csv,.xlsx,.xls,.xlsm,.xlsb,.tsv,.txt"
              loading={uploading === "product_info"}
              onFile={(f) => void handleProductInfoUpload(f)}
            />
          </CardContent>
        </Card>
      </div>

      <Card className="flex min-h-0 flex-1 flex-col">
        <CardHeader className="flex shrink-0 flex-row flex-wrap items-center justify-between gap-2 pb-3">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-sm">当前产品主数据表</CardTitle>
            <Badge variant="secondary">{items.length} SKU</Badge>
            <Button
              size="sm"
              variant={onlyMissingCustoms ? "destructive" : "outline"}
              onClick={() => setOnlyMissingCustoms((v) => !v)}
              title="品类+HS 没有申报要素模板的产品（如钓具），导出报关会被阻断"
            >
              缺报关配置 {missingCustomsCount}
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            <label className="inline-flex">
              <input
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  const names = { tencent: "腾讯表格", freight: "运费测算表", jiufang: "九方单箱数据" } as const;
                  try {
                    const pv = await previewTicketImport(file);
                    const s = pv.summary;
                    const ok = window.confirm(
                      `${names[pv.source]}：共 ${s.total} 票，新增 ${s.new}、变化 ${s.changed}、不变 ${s.unchanged}` +
                        (pv.issues.length ? `，提示 ${pv.issues.length} 条（${pv.issues[0].message}…）` : "") +
                        "。确认写入？",
                    );
                    if (!ok) return;
                    const res = await applyTicketImport(file);
                    toast.success(`已写入 ${res.tickets_written} 票`);
                  } catch (err) {
                    toast.error(formatApiError(err));
                  }
                }}
              />
              <Button size="sm" variant="outline" className="gap-1.5" asChild>
                <span>
                  <Upload className="h-4 w-4" />
                  导入票级数据
                </span>
              </Button>
            </label>
            <label className="inline-flex">
              <input
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  try {
                    const pv = await previewWarehouseImport(file);
                    const s = pv.summary;
                    const ok = window.confirm(
                      `仓库地址库：共 ${s.total} 条，新增 ${s.new}、变化 ${s.changed}、不变 ${s.unchanged}` +
                        (pv.issues.length ? `，提示 ${pv.issues.length} 条` : "") +
                        "。确认写入？",
                    );
                    if (!ok) return;
                    const res = await applyWarehouseImport(file);
                    toast.success(`已写入 ${res.written} 条仓库地址`);
                  } catch (err) {
                    toast.error(formatApiError(err));
                  }
                }}
              />
              <Button size="sm" variant="outline" className="gap-1.5" asChild>
                <span>
                  <Upload className="h-4 w-4" />
                  导入仓库地址库
                </span>
              </Button>
            </label>
            <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void exportMasterProducts().catch((err) => toast.error(formatApiError(err)))}>
              <FileSpreadsheet className="h-4 w-4" />
              导出产品库
            </Button>
            <label className="inline-flex">
              <input
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (!file) return;
                  try {
                    const pv = await previewProductEdits(file);
                    if (!pv.changes.length) {
                      toast.info(`没有改动` + (pv.errors.length ? `，问题 ${pv.errors.length} 条：${pv.errors.slice(0, 3).map((x) => `第${x.row}行 ${x.field} ${x.message}`).join("；")}` : ""));
                      return;
                    }
                    const lines = pv.changes.slice(0, 15).map((c) => `${c.sku} ${c.field}: ${String(c.old ?? "")} → ${String(c.new)}`);
                    const ok = window.confirm(
                      `将修改 ${pv.changes.length} 个字段（改动记为手填并锁定，MCP 拉取不覆盖；申报价仍领星优先）：\n` +
                        lines.join("\n") + (pv.changes.length > 15 ? "\n…" : "") +
                        (pv.errors.length ? `\n另有 ${pv.errors.length} 条问题不写入` : "") + "\n确认写入？",
                    );
                    if (!ok) return;
                    const res = await applyProductEdits(file);
                    toast.success(`已写入 ${res.written} 个字段`);
                    void loadList();
                  } catch (err) {
                    toast.error(formatApiError(err));
                  }
                }}
              />
              <Button size="sm" variant="outline" className="gap-1.5" asChild>
                <span>
                  <Upload className="h-4 w-4" />
                  导回批量修改
                </span>
              </Button>
            </label>
            <Button
              size="sm"
              className="gap-1.5"
              onClick={() => void handleOpenLocalExcel()}
              disabled={excelOpening || loading}
            >
              {excelOpening ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FileSpreadsheet className="h-4 w-4" />
              )}
              在本地 Excel 批量编辑
            </Button>
            <Button
              size="sm"
              variant="secondary"
              className="gap-1.5"
              onClick={() => void handleSyncLocalExcel()}
              disabled={excelSyncing || loading}
            >
              {excelSyncing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              刷新同步本地修改
            </Button>
          </div>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col p-0 pb-2">
          <MasterDataEditableTable
            items={shownItems}
            loading={loading && !listLoaded}
            onRowUpdated={handleRowUpdated}
            onRowDeleted={handleRowDeleted}
            className="min-h-0 flex-1"
          />
        </CardContent>
      </Card>
    </div>
  );
}
