import { useCallback, useId, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  Loader2,
  Play,
  Sparkles,
  UploadCloud,
  AlertTriangle,
  Scale,
  Package,
  Printer,
  X,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { DEFAULT_THROW_RATIO } from "@/constants";
import { useWorkflow } from "@/context/workflow-context";
import { formatFileSize } from "@/lib/box-editor";
import { useHistoryFilePicker } from "@/hooks/use-history-file-picker";
import { usePreventBrowserFileDrop, fileDropZoneProps } from "@/hooks/use-prevent-browser-file-drop";
import { useShipmentValidation } from "@/hooks/use-shipment-validation";
import { HistoryFilesAccordion } from "@/components/history-files-accordion";
import { StaleDataBanner } from "@/components/stale-data-banner";
import { TableScrollArea } from "@/components/table-scroll-area";
import {
  formatForwarderCell,
  forwarderDimColSpan,
  forwarderTableColumns,
  isForwarderSubtotalRow,
  shouldSkipForwarderCell,
} from "@/lib/forwarder-table";
import {
  formatShippingSheetCell,
  formatShippingSheetLegendCell,
  isShippingSheetNumericColumn,
  SHIPPING_SHEET_LEGEND_COLUMNS,
  SHIPPING_SHEET_LEGEND_SKU_COLSPAN,
  shippingSheetColumns,
  shippingSheetHeaderLabel,
} from "@/lib/shipping-sheet";

function FileChip({
  file,
  kind,
  onRemove,
  isNew,
}: {
  file: File;
  kind: "csv" | "pdf";
  onRemove?: () => void;
  isNew?: boolean;
}) {
  const Icon = kind === "csv" ? FileSpreadsheet : FileText;
  const tone =
    kind === "csv"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : "border-rose-200 bg-rose-50 text-rose-700";
  return (
    <div
      className={cn(
        "flex items-center gap-3 rounded-md border border-border bg-card px-3 py-2 transition-all duration-300",
        isNew && "animate-in fade-in slide-in-from-bottom-2 ring-2 ring-primary/30",
      )}
    >
      <span className={cn("flex h-9 w-9 items-center justify-center rounded-md border", tone)}>
        <Icon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-medium text-foreground">{file.name}</div>
        <div className="text-[10px] text-muted-foreground">
          {formatFileSize(file.size)} · 已选择
        </div>
      </div>
      {onRemove && (
        <Button variant="ghost" size="icon" className="h-7 w-7 shrink-0" onClick={onRemove}>
          <X className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}

function Dropzone({
  title,
  accept,
  files,
  kind,
  onFiles,
  onRemoveAt,
  historyHighlight,
  newFileNames,
}: {
  title: string;
  accept: string;
  files: File[];
  kind: "csv" | "pdf";
  onFiles: (files: File[]) => void;
  onRemoveAt?: (index: number) => void;
  historyHighlight?: boolean;
  newFileNames?: Set<string>;
}) {
  const inputId = useId();
  const [dragOver, setDragOver] = useState(false);
  const acceptExts = accept
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

  const addFiles = (incoming: FileList | null) => {
    if (!incoming?.length) return;
    const picked = Array.from(incoming).filter((file) => {
      if (!acceptExts.length) return true;
      const name = file.name.toLowerCase();
      return acceptExts.some((ext) => name.endsWith(ext.startsWith(".") ? ext : `.${ext}`));
    });
    if (!picked.length) return;
    onFiles([...files, ...picked]);
  };

  const preventDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDragEnter = (e: React.DragEvent) => {
    preventDrag(e);
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    preventDrag(e);
    if (e.currentTarget.contains(e.relatedTarget as Node)) return;
    setDragOver(false);
  };

  const handleDragOver = (e: React.DragEvent) => {
    preventDrag(e);
    e.dataTransfer.dropEffect = "copy";
    setDragOver(true);
  };

  const handleDrop = (e: React.DragEvent) => {
    preventDrag(e);
    setDragOver(false);
    addFiles(e.dataTransfer.files);
  };

  return (
    <div
      {...fileDropZoneProps}
      className="space-y-2"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      <div
        className={cn(
          "relative rounded-lg border-2 border-dashed transition-all duration-500",
          dragOver
            ? "border-primary bg-primary/10"
            : historyHighlight
              ? "border-primary bg-primary/15 shadow-[0_0_0_4px_rgba(var(--primary),0.12)] scale-[1.01]"
              : "border-border bg-muted/30 hover:border-primary/40 hover:bg-primary/[0.03]",
        )}
      >
        <label
          htmlFor={inputId}
          className="flex cursor-pointer flex-col items-center justify-center gap-1 px-4 py-5 text-center"
        >
          <UploadCloud className={cn("h-6 w-6", dragOver ? "text-primary" : "text-muted-foreground")} />
          <div className="text-xs font-medium text-foreground">{title}</div>
          <div className="text-[11px] text-muted-foreground">点击或拖入本地文件，或从下方历史面板点选</div>
        </label>
      </div>
      <input
        id={inputId}
        type="file"
        accept={accept}
        multiple
        className="sr-only"
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => {
          addFiles(e.target.files);
          e.target.value = "";
        }}
      />
      <div className="space-y-1.5">
        {(Array.isArray(files) ? files : []).map((f, i) => (
          <FileChip
            key={`${f.name}-${i}`}
            file={f}
            kind={kind}
            isNew={newFileNames?.has(f.name)}
            onRemove={() => onRemoveAt?.(i)}
          />
        ))}
      </div>
    </div>
  );
}

export function Step4Workspace({ onPrev, onNext }: { onPrev?: () => void; onNext?: () => void }) {
  const { csvFiles, setCsvFiles, pdfFiles, setPdfFiles, throwRatio, setThrowRatio, boxEditorApi, staleness } =
    useWorkflow();

  const {
    validating,
    downloading,
    error,
    progress,
    progressMessage,
    progressLog,
    step4Ok,
    boxLabelMapping,
    mappingOk,
    isStrictMapping,
    amazonLedMode,
    crossCheckOk,
    crossCheckModalOpen,
    setCrossCheckModalOpen,
    crossCheckModalErrors,
    workerPackingLoading,
    workerPackingSuccess,
    shipments,
    actualPlacementFee,
    workerPackingPreview,
    shippingSheet,
    shippingSheetLegend,
    warehouses,
    displayStatusLines,
    displayErrors,
    forwarderDisplay,
    displayLogisticsProfile,
    handleValidate,
    handleWorkerPackingDownload,
    downloadShippingSheet,
    downloadForwarder,
    downloadThermalLabelsPdf,
    downloadWorkerPacking,
    changePackingMode,
    resetValidation,
  } = useShipmentValidation();

  const [selectedHistoryCSVs, setSelectedHistoryCSVs] = useState<Set<string>>(() => new Set());
  const [selectedHistoryPDFs, setSelectedHistoryPDFs] = useState<Set<string>>(() => new Set());
  const [historyPickError, setHistoryPickError] = useState<string | null>(null);
  const [csvSuccessFlashIds, setCsvSuccessFlashIds] = useState<Set<string>>(() => new Set());
  const [pdfSuccessFlashIds, setPdfSuccessFlashIds] = useState<Set<string>>(() => new Set());
  const [csvDropHighlight, setCsvDropHighlight] = useState(false);
  const [pdfDropHighlight, setPdfDropHighlight] = useState(false);
  const [newCsvNames, setNewCsvNames] = useState<Set<string>>(() => new Set());
  const [newPdfNames, setNewPdfNames] = useState<Set<string>>(() => new Set());
  const [historySkipNetworkForMock, setHistorySkipNetworkForMock] = useState(false);

  usePreventBrowserFileDrop();

  const handleHistoryReady = useCallback((meta: { skipNetworkForMock: boolean }) => {
    setHistorySkipNetworkForMock(meta.skipNetworkForMock);
  }, []);

  const flashRowSuccess = useCallback(
    (
      itemId: string,
      fileName: string,
      setFlashIds: React.Dispatch<React.SetStateAction<Set<string>>>,
      setNewNames: React.Dispatch<React.SetStateAction<Set<string>>>,
      setDropHighlight: React.Dispatch<React.SetStateAction<boolean>>,
    ) => {
      setFlashIds((prev) => new Set(prev).add(itemId));
      setNewNames((prev) => new Set(prev).add(fileName));
      setDropHighlight(true);
      window.setTimeout(() => {
        setFlashIds((prev) => {
          const next = new Set(prev);
          next.delete(itemId);
          return next;
        });
        setNewNames((prev) => {
          const next = new Set(prev);
          next.delete(fileName);
          return next;
        });
        setDropHighlight(false);
      }, 750);
    },
    [],
  );

  const csvPicker = useHistoryFilePicker({
    kind: "csv",
    files: csvFiles,
    setFiles: setCsvFiles,
    selectedIds: selectedHistoryCSVs,
    setSelectedIds: setSelectedHistoryCSVs,
    onPickError: setHistoryPickError,
    onAdded: (itemId, fileName) => {
      resetValidation();
      flashRowSuccess(itemId, fileName, setCsvSuccessFlashIds, setNewCsvNames, setCsvDropHighlight);
    },
    skipNetworkForMock: historySkipNetworkForMock,
  });

  const pdfPicker = useHistoryFilePicker({
    kind: "pdf",
    files: pdfFiles,
    setFiles: setPdfFiles,
    selectedIds: selectedHistoryPDFs,
    setSelectedIds: setSelectedHistoryPDFs,
    onPickError: setHistoryPickError,
    onAdded: (itemId, fileName) => {
      resetValidation();
      flashRowSuccess(itemId, fileName, setPdfSuccessFlashIds, setNewPdfNames, setPdfDropHighlight);
    },
    skipNetworkForMock: historySkipNetworkForMock,
  });

  const forwarderCols = forwarderDisplay.length
    ? forwarderTableColumns(forwarderDisplay)
    : [
        "仓库代码",
        "箱数",
        "箱子长(cm)",
        "箱子宽(cm)",
        "箱子高(cm)",
        "实重(kg)",
        "单箱体积重(kg)",
        "总体积重(kg)",
      ];

  const shippingCols = shippingSheet.length
    ? shippingSheetColumns(shippingSheet)
    : shippingSheetColumns([]);

  return (
    <div className="space-y-5 pb-28">
      <StaleDataBanner
        step={4}
        staleness={staleness}
        onRefresh={() => void handleValidate()}
        refreshLabel="重新校验"
        loading={validating}
      />
      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {!amazonLedMode && !boxEditorApi.length && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription className="text-xs">
            严格模式需要 Step 2 装箱方案，用于本地箱号与亚马逊箱唛一一映射。
          </AlertDescription>
        </Alert>
      )}

      <Card className="border-primary/20 bg-gradient-to-r from-muted/30 to-card shadow-sm">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">校验模式</span>
            <Badge variant={isStrictMapping ? "secondary" : "default"}>
              {isStrictMapping
                ? "🤖 严格本地排箱模式 (强校验本地箱号)"
                : "🛠️ 亚马逊主导模式 (仅校验宏观数据)"}
            </Badge>
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground">
            {isStrictMapping
              ? "要求 Step 2 本地箱号与亚马逊箱唛绝对一一对应；本地 Box 映射失败将完整展示并阻断校验。"
              : "工人按亚马逊 CSV/PDF 箱唛装箱；仅校验宏观 SKU 总数与分仓，本地箱号差异不阻断。"}
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Badge variant="secondary" className="h-5 px-1.5 font-mono text-[10px]">
                1
              </Badge>
              亚马逊装箱单 CSV
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Dropzone
              title="拖入 Amazon Packing List CSV"
              accept=".csv"
              files={csvFiles}
              kind="csv"
              historyHighlight={csvDropHighlight}
              newFileNames={newCsvNames}
              onFiles={(f) => {
                setCsvFiles(f);
                resetValidation();
              }}
              onRemoveAt={(index) => {
                csvPicker.removeFileAt(index);
                resetValidation();
              }}
            />
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Badge variant="secondary" className="h-5 px-1.5 font-mono text-[10px]">
                2
              </Badge>
              箱唛 PDF
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Dropzone
              title="拖入 Box Labels PDF"
              accept=".pdf"
              files={pdfFiles}
              kind="pdf"
              historyHighlight={pdfDropHighlight}
              newFileNames={newPdfNames}
              onFiles={(f) => {
                setPdfFiles(f);
                resetValidation();
              }}
              onRemoveAt={(index) => {
                pdfPicker.removeFileAt(index);
                resetValidation();
              }}
            />
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Badge variant="secondary" className="h-5 px-1.5 font-mono text-[10px]">
                3
              </Badge>
              参数与操作
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="divisor" className="text-xs">
                抛重系数
              </Label>
              <Input
                id="divisor"
                type="number"
                value={throwRatio}
                onChange={(e) => setThrowRatio(Number(e.target.value) || DEFAULT_THROW_RATIO)}
                className="font-mono text-sm tabular-nums"
              />
            </div>
            <div className="flex items-start gap-1.5 rounded-md bg-muted/40 px-2.5 py-2 text-[11px] text-muted-foreground">
              <Sparkles className="mt-0.5 h-3 w-3 shrink-0 text-primary" />
              <span>智能换算已开启：in/cm、lb/kg 自动统一度量衡。</span>
            </div>
            <div className="flex items-center justify-between gap-3 rounded-lg border border-primary/25 bg-primary/5 px-3 py-2.5">
              <Label htmlFor="strict-mapping-mode" className="cursor-pointer text-xs font-medium leading-snug">
                {isStrictMapping
                  ? "🤖 严格本地排箱模式 (强校验本地箱号)"
                  : "🛠️ 亚马逊主导模式 (仅校验宏观数据)"}
              </Label>
              <Switch
                id="strict-mapping-mode"
                checked={isStrictMapping}
                onCheckedChange={(checked) => changePackingMode(checked)}
              />
            </div>
            <Button
              className="w-full gap-2 shadow-md"
              disabled={validating || !csvFiles.length || !pdfFiles.length}
              onClick={() => void handleValidate()}
            >
              {validating ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在与物理箱唛进行三维交叉比对...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 fill-current" />
                  开始校验
                </>
              )}
            </Button>
            <Button
              variant="outline"
              className="w-full gap-2 border-amber-300 bg-amber-50/50 hover:bg-amber-50"
              disabled={workerPackingLoading || !csvFiles.length || !pdfFiles.length}
              onClick={() => void handleWorkerPackingDownload()}
            >
              {workerPackingLoading ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  正在与物理箱唛进行三维交叉比对...
                </>
              ) : (
                <>
                  <Printer className="h-4 w-4" />
                  下载工人装箱实操单 (Excel)
                </>
              )}
            </Button>
            {workerPackingSuccess && step4Ok && (
              <p className="text-center text-xs font-medium text-emerald-700">
                ✅ 交叉校验通过，装箱单已生成！
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <HistoryFilesAccordion
        selectedHistoryCSVs={selectedHistoryCSVs}
        selectedHistoryPDFs={selectedHistoryPDFs}
        csvLoadingIds={csvPicker.loadingIds}
        pdfLoadingIds={pdfPicker.loadingIds}
        csvSuccessFlashIds={csvSuccessFlashIds}
        pdfSuccessFlashIds={pdfSuccessFlashIds}
        pickError={historyPickError}
        onHistoryReady={handleHistoryReady}
        onToggleCsv={csvPicker.toggle}
        onTogglePdf={pdfPicker.toggle}
      />

      {(validating || progress > 0) && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">
              {validating
                ? progressMessage || "正在校验货件数据…"
                : step4Ok
                  ? "校验完成"
                  : "校验结束"}
            </span>
            <span
              className={cn(
                "font-mono font-semibold",
                step4Ok ? "text-emerald-600" : "text-muted-foreground",
              )}
            >
              {progress}%
            </span>
          </div>
          <Progress value={progress} className={cn("h-2", step4Ok && "[&>div]:bg-emerald-500")} />
          {validating && progressLog.length > 0 && (
            <div className="max-h-28 space-y-0.5 overflow-y-auto rounded-md border bg-muted/30 px-3 py-2 text-[11px] leading-relaxed text-muted-foreground">
              {progressLog.map((line, i) => (
                <p
                  key={`${i}-${line}`}
                  className={cn(
                    i === progressLog.length - 1 && "font-medium text-foreground",
                  )}
                >
                  {line}
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {displayStatusLines.length > 0 && (
        <Card className="shadow-sm">
          <CardContent className="space-y-1 p-4 text-xs text-muted-foreground">
            {displayStatusLines.map((line, i) => (
              <p
                key={i}
                className={cn(
                  line.startsWith("✅") && "font-medium text-emerald-700",
                  line.startsWith("❌") && isStrictMapping && "font-medium text-destructive",
                  line.startsWith("⚠️") && "text-amber-800",
                  line.startsWith("ℹ️") && "text-sky-800",
                )}
                dangerouslySetInnerHTML={{
                  __html: line.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>"),
                }}
              />
            ))}
          </CardContent>
        </Card>
      )}

      {displayErrors.length > 0 && !step4Ok && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle className="text-sm">校验未通过</AlertTitle>
          <AlertDescription className="max-h-40 overflow-y-auto text-xs">
            <ul className="list-inside list-disc space-y-1">
              {displayErrors.slice(0, 30).map((e, i) => (
                <li key={i}>{e.replace(/\*\*/g, "")}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {step4Ok && !staleness.validation && (
        <Alert className="border-emerald-200 bg-emerald-50">
          <CheckCircle2 className="h-5 w-5 !text-emerald-600" />
          <AlertTitle className="text-base font-semibold text-emerald-800">
            {crossCheckOk ? "三维交叉校验通过！" : "货件校验通过"}
          </AlertTitle>
          <AlertDescription className="text-xs text-emerald-700/90">
            共 {shipments.length} 个货件匹配成功
            {mappingOk && boxLabelMapping.length
              ? `，${boxLabelMapping.length} 箱贴标映射已就绪`
              : ""}
            ，可下载工人装箱实操单/货代表或进入 Step 4.5 发票。
          </AlertDescription>
        </Alert>
      )}
      {step4Ok && staleness.validation && (
        <Alert className="border-amber-300 bg-amber-50 text-amber-950">
          <AlertTriangle className="h-4 w-4 !text-amber-600" />
          <AlertTitle className="text-sm font-semibold">上次校验通过（已过期）</AlertTitle>
          <AlertDescription className="text-xs">
            上游数据已变更。可对照下方上一版结果，但须重新校验后才能下载正式文件。
          </AlertDescription>
        </Alert>
      )}

      {actualPlacementFee && (
        <Card className="border-emerald-200 bg-gradient-to-r from-emerald-50/60 to-card shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm text-emerald-900">
              💰 入库配置费 · 预估 → 锁定
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs">
            <div className="flex flex-wrap items-baseline gap-3">
              <span className="text-3xl font-bold tabular-nums text-emerald-900">
                ${actualPlacementFee.locked_usd.toFixed(2)}
              </span>
              <span className="text-muted-foreground">保守上限</span>
              {actualPlacementFee.applicable_range_mid_usd !== undefined && (
                <span className="text-emerald-900">
                  预期{" "}
                  <span className="font-semibold tabular-nums">
                    ${actualPlacementFee.applicable_range_mid_usd.toFixed(2)}
                  </span>
                </span>
              )}
              <Badge variant="outline" className="border-emerald-400 text-emerald-900">
                {actualPlacementFee.scenario_label}
              </Badge>
              <span className="text-muted-foreground">
                {actualPlacementFee.actual_location_count} 个目的仓 ·{" "}
                {actualPlacementFee.warehouse_regions.join(" / ")}
              </span>
            </div>
            <div className="grid gap-2 sm:grid-cols-3">
              <FeeCompareCell
                label="Step 1 单点入仓预估"
                min={actualPlacementFee.step1_preview.one_location.min_usd}
                max={actualPlacementFee.step1_preview.one_location.max_usd}
              />
              <FeeCompareCell
                label="Step 1 部分拆分预估"
                min={actualPlacementFee.step1_preview.split_2_3.min_usd}
                max={actualPlacementFee.step1_preview.split_2_3.max_usd}
              />
              <FeeCompareCell
                label="本次适用区间 → 锁定"
                min={actualPlacementFee.applicable_range_min_usd}
                max={actualPlacementFee.applicable_range_max_usd}
                highlight
              />
            </div>
            <p className="font-mono text-[11px] text-muted-foreground">
              目的仓：{actualPlacementFee.actual_warehouses.join(", ")}
            </p>
          </CardContent>
        </Card>
      )}

      {(step4Ok || workerPackingPreview.length > 0) && workerPackingPreview.length > 0 && (
        <Tabs defaultValue={boxLabelMapping.length ? "mapping" : "worker_packing"} className="space-y-3">
          <TabsList
            className={cn(
              "grid w-full max-w-3xl",
              boxLabelMapping.length ? "grid-cols-4" : "grid-cols-3",
            )}
          >
            {boxLabelMapping.length > 0 && (
              <TabsTrigger value="mapping">贴标映射</TabsTrigger>
            )}
            <TabsTrigger value="worker_packing">工人装箱实操单预览</TabsTrigger>
            <TabsTrigger value="shipping_sheet">发货表预览</TabsTrigger>
            <TabsTrigger value="forwarder">货代表预览</TabsTrigger>
          </TabsList>

          {boxLabelMapping.length > 0 && (
            <TabsContent value="mapping">
              <p className="mb-2 text-xs text-muted-foreground">
                Step 2 本地箱号与亚马逊 FBA 箱唛一一对应；工人按此表贴标，避免串货。
              </p>
              <TableScrollArea>
                <table className="w-full border-collapse text-xs">
                  <thead>
                    <tr className="bg-muted/60">
                      {["本地箱号", "装箱内容", "FBA箱号", "目的仓", "货件编号"].map((col) => (
                        <th
                          key={col}
                          className="border-b border-border px-3 py-2 text-left font-semibold"
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {boxLabelMapping.map((row, ri) => (
                      <tr key={ri} className="border-b border-border hover:bg-muted/20">
                        <td className="px-3 py-2 font-mono font-semibold">{row.本地箱号}</td>
                        <td className="px-3 py-2">{row.装箱内容}</td>
                        <td className="px-3 py-2 font-mono text-[11px]">{row.FBA箱号}</td>
                        <td className="px-3 py-2 font-mono">{row.目的仓}</td>
                        <td className="px-3 py-2 font-mono text-[11px]">{row.货件编号}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </TableScrollArea>
            </TabsContent>
          )}

          <TabsContent value="worker_packing">
            <p className="mb-2 text-xs text-muted-foreground">
              按目的仓横向并排，与导出的工人装箱贴标实操单一致。
            </p>
            <TableScrollArea>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="bg-muted/60">
                    {warehouses.flatMap((wh) => [
                      <th
                        key={`${wh}-box`}
                        className="border-b border-border px-3 py-2 text-left font-semibold"
                      >
                        {wh} · 纸箱
                      </th>,
                      <th
                        key={`${wh}-prod`}
                        className="border-b border-border px-3 py-2 text-left font-semibold"
                      >
                        {wh} · 产品
                      </th>,
                      <th
                        key={`${wh}-fnsku`}
                        className="border-b border-border px-3 py-2 text-left font-semibold"
                      >
                        {wh} · FNSKU
                      </th>,
                      <th
                        key={`${wh}-qty`}
                        className="border-b border-border px-3 py-2 text-left font-semibold"
                      >
                        {wh} · 数量
                      </th>,
                    ])}
                  </tr>
                </thead>
                <tbody>
                  {workerPackingPreview.map((row, ri) => {
                    const isSummaryRow = warehouses.some((wh) => {
                      const box = String(row[`${wh}_纸箱编号`] ?? "").trim();
                      const prod = String(row[`${wh}_产品名称`] ?? "").trim();
                      return box === "【汇总】" || (!box && prod.includes("共") && prod.endsWith("箱"));
                    });
                    return (
                    <tr
                      key={ri}
                      className={cn(
                        "border-b border-border",
                        isSummaryRow
                          ? "bg-muted/40 font-semibold text-foreground"
                          : "hover:bg-muted/20",
                      )}
                    >
                      {warehouses.flatMap((wh) => {
                        const boxVal = String(row[`${wh}_纸箱编号`] ?? "");
                        const prodVal = String(row[`${wh}_产品名称`] ?? "");
                        const fnskuVal = String(row[`${wh}_FNSKU`] ?? "");
                        const qtyVal = String(row[`${wh}_数量`] ?? "");
                        const cellSummary =
                          boxVal.trim() === "【汇总】" ||
                          (!boxVal.trim() && prodVal.includes("共") && prodVal.endsWith("箱"));
                        return [
                        <td
                          key={`${wh}-box-${ri}`}
                          className={cn("px-3 py-2 font-mono text-xs", cellSummary && "font-semibold")}
                        >
                          {boxVal}
                        </td>,
                        <td
                          key={`${wh}-prod-${ri}`}
                          className={cn("px-3 py-2 text-xs", cellSummary && "font-semibold")}
                        >
                          {prodVal}
                        </td>,
                        <td
                          key={`${wh}-fnsku-${ri}`}
                          className={cn("px-3 py-2 font-mono text-xs", cellSummary && "font-semibold")}
                        >
                          {fnskuVal}
                        </td>,
                        <td
                          key={`${wh}-qty-${ri}`}
                          className={cn("px-3 py-2 text-xs tabular-nums", cellSummary && "font-semibold")}
                        >
                          {qtyVal}
                        </td>,
                      ];
                      })}
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </TableScrollArea>
          </TabsContent>

          <TabsContent value="shipping_sheet">
            <p className="mb-2 text-xs text-muted-foreground">
              亚马逊 FBA 发货装箱单：按货件/FNSKU 汇总，与导出的发货表一致。
            </p>
            {shippingSheetLegend.length > 0 && (
              <div className="mb-3 rounded-md border border-border bg-muted/30 p-2">
                <p className="mb-1 text-[10px] font-medium text-muted-foreground">Step 1 录入摘要</p>
                <TableScrollArea maxHeight="10rem" variant="plain">
                  <table className="w-full border-collapse text-xs">
                    <thead>
                      <tr className="bg-muted/60">
                        {SHIPPING_SHEET_LEGEND_COLUMNS.map((col) => (
                          <th
                            key={col}
                            colSpan={col === "SKU简称" ? SHIPPING_SHEET_LEGEND_SKU_COLSPAN : 1}
                            className={cn(
                              "border-b border-border px-2 py-1.5 text-left font-semibold",
                              col === "SKU简称" && "min-w-[360px]",
                            )}
                          >
                            {col}*
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {shippingSheetLegend.map((row, ri) => (
                        <tr key={ri} className="border-b border-border">
                          {SHIPPING_SHEET_LEGEND_COLUMNS.map((col) => (
                            <td
                              key={col}
                              colSpan={col === "SKU简称" ? SHIPPING_SHEET_LEGEND_SKU_COLSPAN : 1}
                              className={cn(
                                "px-2 py-1.5 font-mono text-xs",
                                col === "SKU简称" && "whitespace-nowrap",
                              )}
                            >
                              {formatShippingSheetLegendCell(col, row)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </TableScrollArea>
              </div>
            )}
            <TableScrollArea>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="bg-muted/60">
                    {shippingCols.map((col) => {
                      const { cn, en } = shippingSheetHeaderLabel(col);
                      return (
                        <th
                          key={col}
                          className="border-b border-border px-3 py-2 text-left font-semibold"
                        >
                          <div className="leading-tight">{cn}</div>
                          {en && (
                            <div className="text-[10px] font-normal text-muted-foreground">
                              {en}
                            </div>
                          )}
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {shippingSheet.map((row, ri) => (
                    <tr key={ri} className="border-b border-border hover:bg-muted/20">
                      {shippingCols.map((col) => (
                        <td
                          key={col}
                          className={cn(
                            "px-3 py-2 text-xs",
                            isShippingSheetNumericColumn(col) ? "font-mono" : "",
                          )}
                        >
                          {formatShippingSheetCell(col, row)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableScrollArea>
          </TabsContent>

          <TabsContent value="forwarder">
            {displayLogisticsProfile && (
              <div className="mb-3 rounded-lg border border-border bg-gradient-to-r from-muted/40 to-card p-4 shadow-sm">
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="text-xs font-semibold text-foreground">货件宏观画像</span>
                  {displayLogisticsProfile.total_cbm != null && (
                    <Badge className="gap-1 border-amber-300 bg-amber-50 px-2.5 py-0.5 text-xs font-bold text-amber-900 hover:bg-amber-50">
                      总方数: {displayLogisticsProfile.total_cbm.toFixed(3)} CBM
                    </Badge>
                  )}
                  {displayLogisticsProfile.wm_ratio && (
                    <Badge
                      variant="outline"
                      className={cn(
                        "gap-1 text-xs font-medium",
                        displayLogisticsProfile.wm_ratio.includes("Weight")
                          ? "border-slate-700 bg-slate-800 text-white hover:bg-slate-800"
                          : "border-sky-200 bg-sky-50 text-sky-800 hover:bg-sky-50",
                      )}
                    >
                      {displayLogisticsProfile.wm_ratio.includes("Weight") ? (
                        <Scale className="h-3 w-3" />
                      ) : (
                        <Package className="h-3 w-3" />
                      )}
                      {displayLogisticsProfile.wm_ratio}
                    </Badge>
                  )}
                </div>
                <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
                  <span>
                    S.F. (积载因数):{" "}
                    <strong className="font-mono text-foreground">
                      {displayLogisticsProfile.stowage_factor?.toFixed(3) ?? "—"}
                    </strong>
                  </span>
                  <span>
                    总方数:{" "}
                    <strong className="font-mono font-semibold text-amber-800">
                      {displayLogisticsProfile.total_cbm?.toFixed(3) ?? "—"} CBM
                    </strong>
                  </span>
                  <span>
                    货物密度:{" "}
                    <strong className="font-mono text-foreground">
                      {displayLogisticsProfile.cargo_density?.toFixed(3) ?? "—"} kg/CBM
                    </strong>
                  </span>
                  <span>
                    计费吨 (RT):{" "}
                    <strong className="font-mono text-foreground">
                      {displayLogisticsProfile.revenue_ton?.toFixed(3) ?? "—"} kg
                    </strong>
                  </span>
                  <span>
                    毛重 / 体积重:{" "}
                    <strong className="font-mono text-foreground">
                      {displayLogisticsProfile.total_gross_kg?.toFixed(2) ?? "—"} /{" "}
                      {displayLogisticsProfile.total_volumetric_weight_kg?.toFixed(2) ?? "—"} kg
                    </strong>
                  </span>
                </div>
              </div>
            )}
            <TableScrollArea>
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="bg-muted/60">
                    {forwarderCols.map((col) => (
                      <th
                        key={col}
                        className="border-b border-border px-3 py-2 text-left font-semibold"
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {forwarderDisplay.map((row, ri) => {
                    const subtotal = isForwarderSubtotalRow(row);
                    return (
                      <tr
                        key={ri}
                        className={cn(
                          "border-b border-border",
                          subtotal
                            ? "bg-sky-50 font-semibold text-foreground hover:bg-sky-50/90"
                            : "hover:bg-muted/20",
                        )}
                      >
                        {forwarderCols.map((col) => {
                          if (shouldSkipForwarderCell(col, row)) return null;
                          const dimSpan = col === "箱子长(cm)" ? forwarderDimColSpan(row) : undefined;
                          return (
                            <td
                              key={col}
                              colSpan={dimSpan}
                              className={cn(
                                "px-3 py-2 text-xs",
                                subtotal ? "font-semibold" : "font-mono",
                                subtotal && dimSpan ? "text-sky-900" : "",
                              )}
                            >
                              {formatForwarderCell(col, row)}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </TableScrollArea>
          </TabsContent>
        </Tabs>
      )}

      <Dialog open={crossCheckModalOpen} onOpenChange={setCrossCheckModalOpen}>
        <DialogContent className="max-w-lg border-destructive/40">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              三维交叉校验未通过
            </DialogTitle>
            <DialogDescription>
              检测到以下问题，已阻断工人装箱实操单导出。请修正 CSV/PDF 后重试。
            </DialogDescription>
          </DialogHeader>
          <ul className="max-h-72 space-y-2 overflow-y-auto text-sm">
            {crossCheckModalErrors.map((e, i) => (
              <li
                key={i}
                className="rounded-md border border-destructive/20 bg-destructive/5 px-3 py-2 text-destructive"
              >
                {e.replace(/\*\*/g, "")}
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>

      <div className="fixed bottom-0 left-[var(--app-sidebar-width,340px)] right-0 z-10 border-t border-border bg-card/95 px-6 py-3 backdrop-blur supports-[backdrop-filter]:bg-card/80">
        <div className="flex items-center justify-between gap-4">
          <Button variant="outline" size="lg" onClick={onPrev} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            返回 Step 3
          </Button>
          <div className="flex items-center gap-2">
            {step4Ok && (
              <>
                <Button
                  variant="secondary"
                  size="lg"
                  className="gap-2"
                  disabled={!!downloading || workerPackingLoading || staleness.validation}
                  title={staleness.validation ? "结果已过期，不能作为正式文件下载" : undefined}
                  onClick={() => void downloadWorkerPacking()}
                >
                  {downloading === "worker_packing" || workerPackingLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  下载工人装箱实操单 (.xlsx)
                </Button>
                <Button
                  variant="secondary"
                  size="lg"
                  className="gap-2"
                  disabled={!!downloading || !shippingSheet.length || staleness.validation}
                  title={staleness.validation ? "结果已过期，不能作为正式文件下载" : undefined}
                  onClick={() => void downloadShippingSheet()}
                >
                  {downloading === "shipping_sheet" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  下载发货表 (.xlsx)
                </Button>
                <Button
                  variant="secondary"
                  size="lg"
                  className="gap-2"
                  disabled={!!downloading || !shipments.length || staleness.validation}
                  title={staleness.validation ? "结果已过期，不能作为正式文件下载" : undefined}
                  onClick={() => void downloadThermalLabelsPdf()}
                >
                  {downloading === "thermal_labels" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Printer className="h-4 w-4" />
                  )}
                  下载 10×10 热敏箱贴 (PDF)
                </Button>
                <Button
                  variant="secondary"
                  size="lg"
                  className="gap-2"
                  disabled={!!downloading || staleness.validation}
                  title={staleness.validation ? "结果已过期，不能作为正式文件下载" : undefined}
                  onClick={() => void downloadForwarder()}
                >
                  {downloading === "forwarder" ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  下载货代表 (.xlsx)
                </Button>
              </>
            )}
          </div>
          <Button
            size="lg"
            disabled={!step4Ok && !shipments.length}
            onClick={onNext}
            className="gap-2 bg-gradient-to-r from-primary to-primary/80 px-6 text-base font-semibold shadow-md"
          >
            <Sparkles className="h-4 w-4" />
            进入 Step 4.5 发票
            <ArrowRight className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function FeeCompareCell({
  label,
  min,
  max,
  highlight,
}: {
  label: string;
  min: number | null | undefined;
  max: number | null | undefined;
  highlight?: boolean;
}) {
  const text =
    min == null || max == null
      ? "—"
      : min === max
        ? `$${min.toFixed(2)}`
        : `$${min.toFixed(2)} – $${max.toFixed(2)}`;
  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2",
        highlight ? "border-emerald-300 bg-emerald-50/50" : "border-border bg-muted/20",
      )}
    >
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 font-semibold tabular-nums", highlight && "text-emerald-900")}>
        {text}
      </div>
    </div>
  );
}
