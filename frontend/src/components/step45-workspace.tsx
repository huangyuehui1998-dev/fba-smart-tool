import { useRef, useState } from "react";
import { ForwarderInvoiceExportPanel } from "@/components/forwarder-invoice-export-panel";
import { InvoiceTemplateRecognizePanel } from "@/components/invoice-template-recognize-panel";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ClipboardCopy,
  Info,
  Lightbulb,
  Link2,
  Loader2,
  Play,
  Plus,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { fileDropZoneProps, usePreventBrowserFileDrop } from "@/hooks/use-prevent-browser-file-drop";
import { useInvoice } from "@/hooks/use-invoice";
import { useWorkflow } from "@/context/workflow-context";
import { StaleDataBanner } from "@/components/stale-data-banner";
import { InvoiceSpreadsheet } from "@/components/invoice-spreadsheet";
import { CELL_SOURCE_STYLES, type CellSourceKind } from "@/lib/invoice-spreadsheet";

const LEGEND_KEYS: CellSourceKind[] = ["exact", "local", "missing"];

export function Step45Workspace({ onPrev, onNext }: { onPrev?: () => void; onNext?: () => void }) {
  const { staleness } = useWorkflow();
  const {
    shipments,
    step4Ok,
    selectedShipmentId,
    filledShipmentIds,
    syncLinkedEdits,
    setSyncLinkedEdits,
    spreadsheetRef,
    sheetPhase,
    templateReady,
    setTemplateReady,
    parsing,
    filling,
    exporting,
    copying,
    error,
    setError,
    hasTemplate,
    canAutoFill,
    gridLoading,
    revenueTon,
    missingLabels,
    hasMissing,
    forwarders,
    forwardersLoading,
    selectedForwarderId,
    poNumber,
    addDialogOpen,
    setAddDialogOpen,
    savingForwarder,
    runFill,
    runFillAllValidated,
    handleExport,
    handleCopyToExcel,
    handleForwarderChange,
    handleAddForwarder,
    handleCellEdited,
    handleShipmentChange,
    handlePoChange,
  } = useInvoice();

  const newFwdNameRef = useRef<HTMLInputElement>(null);
  const newFwdFileRef = useRef<HTMLInputElement>(null);
  const [newFwdFile, setNewFwdFile] = useState<File | null>(null);

  usePreventBrowserFileDrop();

  const submitNewForwarder = () => {
    const name = newFwdNameRef.current?.value.trim() ?? "";
    const file = newFwdFile ?? newFwdFileRef.current?.files?.[0];
    if (!name || !file) {
      setError("请填写货代名称并上传 .xlsx 模板");
      return;
    }
    void handleAddForwarder(name, file);
  };

  if (!shipments.length) {
    return (
      <div className="space-y-5">
      <ForwarderInvoiceExportPanel />
      <InvoiceTemplateRecognizePanel />
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>无法生成发票</AlertTitle>
        <AlertDescription>请先在 Step 4 完成 CSV/PDF 校验。</AlertDescription>
        <Button variant="outline" size="sm" className="mt-3" onClick={onPrev}>
          返回 Step 4
        </Button>
      </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-5 pb-28">
      <StaleDataBanner step={4.5} staleness={staleness} />
      <ForwarderInvoiceExportPanel />
      <InvoiceTemplateRecognizePanel />
      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Alert className="border-sky-200 bg-sky-50">
        <Lightbulb className="h-4 w-4 !text-sky-600" />
        <AlertDescription className="text-xs text-sky-800">
          选择货代后自动加载发票模板；数据按 Step1/2 → Step4 → 产品库 填充，找不到则留空。PO
          号在下方手填。预览支持编辑，可复制带格式表格到 Excel。
        </AlertDescription>
      </Alert>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="shadow-sm">
          <CardContent className="space-y-3 p-4">
            <Label className="text-xs font-medium">货代（发票模板）</Label>
            <div className="flex gap-2">
              <Select
                value={selectedForwarderId}
                onValueChange={(id) => void handleForwarderChange(id)}
                disabled={forwardersLoading || parsing}
              >
                <SelectTrigger className="h-11 flex-1">
                  <SelectValue placeholder={forwardersLoading ? "加载货代…" : "选择货代"} />
                </SelectTrigger>
                <SelectContent>
                  {forwarders.map((f) => (
                    <SelectItem key={f.id} value={f.id}>
                      {f.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="h-11 w-11 shrink-0"
                title="新增货代"
                onClick={() => setAddDialogOpen(true)}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
            {parsing && (
              <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                正在加载模板…
              </p>
            )}
            {hasTemplate && !parsing && (
              <p className="text-[11px] text-emerald-700">
                {sheetPhase === "preview"
                  ? "预览态"
                  : sheetPhase === "filled"
                    ? "填充态"
                    : "已加载"}{" "}
                · Excel 原样排版已就绪
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="shadow-sm lg:col-span-2">
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label className="text-xs font-medium">校验通过货件</Label>
              <label className="flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground">
                <input
                  type="checkbox"
                  className="rounded border-border"
                  checked={syncLinkedEdits}
                  onChange={(e) => setSyncLinkedEdits(e.target.checked)}
                />
                <Link2 className="h-3 w-3" />
                联动修改相同属性
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              {shipments.map((s) => {
                const active = s.shipment_id === selectedShipmentId;
                const filled = filledShipmentIds.includes(s.shipment_id);
                return (
                  <button
                    key={s.shipment_id}
                    type="button"
                    onClick={() => void handleShipmentChange(s.shipment_id)}
                    className={cn(
                      "rounded-md border px-3 py-2 text-left text-xs transition-colors",
                      active
                        ? "border-primary bg-primary/10 text-foreground"
                        : "border-border bg-background hover:bg-muted/50",
                    )}
                  >
                    <span className="block font-mono font-semibold">{s.shipment_id}</span>
                    <span className="text-muted-foreground">{s.warehouse}</span>
                    {filled && (
                      <span className="mt-0.5 block text-[10px] text-emerald-600 dark:text-emerald-400">
                        已填写
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
            <Label className="text-xs font-medium">PO 号（POAnumber）</Label>
            <Input
              className="h-10 font-mono text-sm"
              placeholder="手填 PO，如 3LK7RGCJ"
              value={poNumber}
              onChange={(e) => handlePoChange(e.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="lg"
                className="h-11 flex-1 gap-2 bg-orange-600 text-base font-semibold shadow-md hover:bg-orange-700"
                disabled={!canAutoFill}
                onClick={() => void runFill()}
              >
                {filling ? (
                  <>
                    <Loader2 className="h-5 w-5 animate-spin" />
                    填写中…
                  </>
                ) : (
                  <>
                    <Play className="h-5 w-5 fill-current" />
                    开始自动填写
                  </>
                )}
              </Button>
              <Button
                type="button"
                size="lg"
                variant="outline"
                className="h-11 gap-2"
                disabled={!canAutoFill || shipments.length < 2}
                onClick={() => void runFillAllValidated()}
              >
                全部填写
              </Button>
            </div>
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <Info className="h-3 w-3 shrink-0" />
              仅展示 Step 4 校验通过货件 · 点击货件切换预览
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardContent className="flex h-full flex-col justify-center gap-3 p-4">
            <Button
              type="button"
              variant="outline"
              size="lg"
              className="h-11 w-full gap-2"
              disabled={!hasTemplate || copying}
              onClick={() => void handleCopyToExcel()}
            >
              {copying ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  复制中…
                </>
              ) : (
                <>
                  <ClipboardCopy className="h-4 w-4" />
                  复制到 Excel（含格式）
                </>
              )}
            </Button>
            <p className="text-center text-[11px] text-muted-foreground">
              保留合并单元格、边框与列宽，在 Excel 中直接粘贴
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {revenueTon != null && sheetPhase === "filled" && (
          <Badge
            variant="outline"
            className="w-fit border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-normal text-emerald-900 hover:bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100"
          >
            计费吨 (RT): <strong className="font-mono">{revenueTon.toFixed(3)}</strong> kg
          </Badge>
        )}
        {selectedShipmentId && (
          <Badge variant="secondary" className="font-mono text-xs">
            当前货件: {selectedShipmentId}
          </Badge>
        )}
      </div>

      {sheetPhase === "filled" && hasTemplate && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-border bg-card px-4 py-2.5 text-xs">
          <span className="font-semibold text-foreground">填充态 · 来源图例</span>
          {LEGEND_KEYS.map((k) => (
            <span key={k} className="flex items-center gap-1.5 text-muted-foreground">
              <span
                className={cn("h-4 w-6 rounded border border-border", CELL_SOURCE_STYLES[k].bg)}
              />
              {CELL_SOURCE_STYLES[k].label}
            </span>
          ))}
        </div>
      )}

      <InvoiceSpreadsheet
        ref={spreadsheetRef}
        loading={gridLoading}
        onReadyChange={setTemplateReady}
        onLoadError={(msg) => setError(msg)}
        onCellEdited={handleCellEdited}
      />

      {hasMissing && (
        <Alert className="border-amber-300 bg-amber-50">
          <AlertTriangle className="h-4 w-4 !text-amber-600" />
          <AlertTitle className="text-sm font-semibold text-amber-900">部分字段未填</AlertTitle>
          <AlertDescription className="text-xs text-amber-800">
            以下仍为空：{missingLabels.join("、")}。可导出后在 Excel 中补全。
          </AlertDescription>
        </Alert>
      )}

      <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>新增货代</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="fwd-name">货代名称</Label>
              <Input id="fwd-name" ref={newFwdNameRef} placeholder="如：琪珞国际" />
            </div>
            <div className="space-y-1.5">
              <Label>发票模板 (.xlsx)</Label>
              <div {...fileDropZoneProps}>
                <label className="flex cursor-pointer flex-col items-center gap-1 rounded-lg border border-dashed border-border px-4 py-5 text-center text-sm hover:bg-muted/40">
                  {newFwdFile ? newFwdFile.name : "点击或拖拽上传模板"}
                  <input
                    ref={newFwdFileRef}
                    type="file"
                    accept=".xlsx"
                    className="sr-only"
                    onChange={(e) => setNewFwdFile(e.target.files?.[0] ?? null)}
                  />
                </label>
              </div>
              <p className="text-[11px] text-muted-foreground">
                表头中文名将自动识别列映射（如 FBAID、箱序号、物品中文名等）
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddDialogOpen(false)}>
              取消
            </Button>
            <Button disabled={savingForwarder} onClick={submitNewForwarder}>
              {savingForwarder ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  保存中…
                </>
              ) : (
                "保存"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="fixed bottom-0 left-[var(--app-sidebar-width,340px)] right-0 z-10 border-t border-border bg-card/95 px-6 py-3 backdrop-blur transition-[left] duration-300 ease-in-out supports-[backdrop-filter]:bg-card/80">
        <div className="flex items-center justify-between gap-4">
          <Button variant="outline" size="lg" onClick={onPrev} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            返回 Step 4
          </Button>
          <div className="flex items-center gap-2">
            {onNext && (
              <Button variant="secondary" size="lg" className="gap-2" onClick={onNext}>
                Step 5 报关资料
                <ArrowRight className="h-4 w-4" />
              </Button>
            )}
            <Button
              size="lg"
              disabled={sheetPhase !== "filled" || !hasTemplate || exporting || staleness.invoice}
              title={staleness.invoice ? "结果已过期，不能作为正式文件下载" : undefined}
              className="gap-2 px-8 text-base font-semibold shadow-md"
              onClick={() => void handleExport()}
            >
            {exporting ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                导出中…
              </>
            ) : (
              <>
                导出最终发票
                <ArrowRight className="h-5 w-5" />
              </>
            )}
          </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
