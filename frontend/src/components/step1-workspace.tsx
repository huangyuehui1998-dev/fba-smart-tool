import { useState } from "react";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import {
  Sparkles,
  Download,
  Upload,
  Plus,
  AlertTriangle,
  Package,
  Scale,
  Cuboid,
  Weight,
  ArrowRight,
  Loader2,
  Trash2,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { TableScrollArea } from "@/components/table-scroll-area";
import { Step1CostDashboard } from "@/components/step1-cost-dashboard";
import { emptyComputed, type ComputedDisplay } from "@/lib/step1-rows";
import { usePreventBrowserFileDrop } from "@/hooks/use-prevent-browser-file-drop";
import { useStep1Logic } from "@/hooks/use-step1-logic";
import { MasterDataGapBanner } from "@/components/master-data-gap-banner";
import { step1FixHint, summarizeStep1Issues, visibleStep1Indexes } from "@/lib/step1-issues";

const EDITABLE_COLS = [
  { key: "sku", label: "SKU简称", w: "min-w-[120px]" },
  { key: "fnsku", label: "FNSKU", w: "min-w-[130px]" },
  { key: "totalQty", label: "发货总数", w: "min-w-[90px]" },
  { key: "perBox", label: "单箱装量", w: "min-w-[90px]" },
  { key: "l", label: "箱长(cm)", w: "min-w-[85px]" },
  { key: "w", label: "箱宽(cm)", w: "min-w-[85px]" },
  { key: "h", label: "箱高(cm)", w: "min-w-[85px]" },
  { key: "unitKg", label: "单个重量(kg)", w: "min-w-[100px]" },
  { key: "emptyKg", label: "空纸箱重(kg)", w: "min-w-[100px]" },
  { key: "grossKg", label: "单箱毛重(kg)", w: "min-w-[100px]" },
] as const;

const COMPUTED_COLS = [
  { key: "fullBoxes", label: "预计整箱数" },
  { key: "remainder", label: "尾数" },
  { key: "netKg", label: "预计总净重(kg)" },
  { key: "grossTotalKg", label: "预计总毛重(kg)" },
];

export function Step1Workspace({ onNext }: { onNext?: () => void }) {
  usePreventBrowserFileDrop();

  const [onlyIssues, setOnlyIssues] = useState(false);
  const [fixRow, setFixRow] = useState<number | null>(null);
  const [fixUnit, setFixUnit] = useState("");
  const {
    rows,
    text,
    setText,
    computed,
    totalCbm,
    totalVolWeight,
    cargoDensity,
    costDashboard,
    actualPlacementFee,
    validationErrors,
    weightWarnings,
    masterGaps,
    weightConfirmOpen,
    keepDeclaredWeights,
    useCalculatedWeights,
    applyUnitWeightFix,
    parseAction,
    previewLoading,
    error,
    success,
    fileInputRef,
    excelInputId,
    totals: { totalFullBoxes, totalNet, totalGross },
    update,
    applySpec,
    cartonSpecsBySku,
    cartonSpecNotices,
    addRow,
    removeRow,
    handleParseLocal,
    handleParseDeepseek,
    handleExcelUpload,
    handleDownloadTemplate,
  } = useStep1Logic();

  const issueSummary = summarizeStep1Issues(validationErrors, weightWarnings);
  const shownIndexes = visibleStep1Indexes(rows.length, issueSummary, onlyIssues);

  return (
    <div className="space-y-6 pb-32">
      <MasterDataGapBanner gaps={masterGaps} />
      {(error || success) && (
        <div className="space-y-2">
          {error && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle className="text-sm">操作失败</AlertTitle>
              <AlertDescription className="text-xs">{error}</AlertDescription>
            </Alert>
          )}
          {success && (
            <Alert className="border-emerald-200 bg-emerald-50 text-emerald-900">
              <AlertTitle className="text-sm font-semibold text-emerald-800">解析成功</AlertTitle>
              <AlertDescription className="text-xs text-emerald-700">{success}</AlertDescription>
            </Alert>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">快捷导入 · 智能文本</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="例：DEMO-SKU-001 共120个，单箱20个，箱规45*32*28，单重0.35kg，毛重7.5kg…"
              className="min-h-[140px] resize-none text-sm"
              disabled={parseAction === "local" || parseAction === "deepseek"}
            />
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void handleParseLocal()}
                disabled={parseAction !== null}
              >
                {parseAction === "local" ? (
                  <>
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                    解析中…
                  </>
                ) : (
                  "本地规则解析"
                )}
              </Button>
              <Button
                size="sm"
                className="gap-1.5"
                onClick={() => void handleParseDeepseek()}
                disabled={parseAction !== null}
              >
                {parseAction === "deepseek" ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    DeepSeek 解析中…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" />
                    DeepSeek 智能解析
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base">快捷导入 · Excel（推荐）</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary">
                  1
                </span>
                下载标准样表
              </span>
              <span className="text-border">→</span>
              <span className="flex items-center gap-1.5">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary">
                  2
                </span>
                填入 SKU
              </span>
              <span className="text-border">→</span>
              <span className="flex items-center gap-1.5">
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary/10 text-[10px] font-semibold text-primary">
                  3
                </span>
                上传样表
              </span>
            </div>

            <Button
              variant="secondary"
              size="sm"
              className="gap-1.5"
              onClick={() => void handleDownloadTemplate()}
              disabled={parseAction !== null}
            >
              {parseAction === "template" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              下载录入样表(.xlsx)
            </Button>

            <label
              htmlFor={excelInputId}
              onDragOver={(e) => {
                e.preventDefault();
                e.stopPropagation();
              }}
              onDrop={(e) => {
                e.preventDefault();
                e.stopPropagation();
                const file = e.dataTransfer.files?.[0];
                if (file) void handleExcelUpload(file);
              }}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border bg-muted/30 px-4 py-6 text-center transition-colors hover:border-primary/50 hover:bg-muted/50",
                parseAction === "excel" && "pointer-events-none opacity-60",
              )}
            >
              {parseAction === "excel" ? (
                <>
                  <Loader2 className="h-6 w-6 animate-spin text-primary" />
                  <span className="text-sm font-medium text-foreground">正在解析样表…</span>
                </>
              ) : (
                <>
                  <Upload className="h-6 w-6 text-muted-foreground" />
                  <span className="text-sm font-medium text-foreground">
                    拖拽或点击上传填好的样表
                  </span>
                  <span className="text-xs text-muted-foreground">支持 .xlsx / .xls</span>
                </>
              )}
            </label>
            <input
              id={excelInputId}
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              className="sr-only"
              disabled={parseAction !== null}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) void handleExcelUpload(file);
                e.target.value = "";
              }}
            />
          </CardContent>
        </Card>
      </div>

      {cartonSpecNotices.length > 0 && (
        <div className="space-y-1 text-xs text-amber-800">
          {cartonSpecNotices.map((notice) => (
            <p key={notice}>{notice}</p>
          ))}
        </div>
      )}

      <Card className="shadow-sm">
        <CardHeader className="flex flex-row items-center justify-between gap-3 pb-3">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">可编辑数据网格</CardTitle>
            <button
              type="button"
              data-testid="issue-count-block"
              className="rounded border border-red-200 bg-red-50 px-2 py-0.5 text-xs text-red-800"
              onClick={() => setOnlyIssues(true)}
            >
              阻断 {issueSummary.blockCount}
            </button>
            <button
              type="button"
              data-testid="issue-count-warn"
              className="rounded border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs text-amber-900"
              onClick={() => setOnlyIssues((on) => !on)}
            >
              警告 {issueSummary.warnCount}
            </button>
            {onlyIssues && (
              <button type="button" className="text-xs text-muted-foreground underline" onClick={() => setOnlyIssues(false)}>
                显示全部
              </button>
            )}
          </div>
          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
            {previewLoading && (
              <span className="flex items-center gap-1 text-primary">
                <Loader2 className="h-3 w-3 animate-spin" />
                计算中…
              </span>
            )}
            <span className="flex items-center gap-1.5">
              <span className="h-3 w-3 rounded-sm border border-border bg-background" />
              可编辑
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-3 w-3 rounded-sm border border-border bg-muted" />
              后端实时计算
            </span>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <TableScrollArea variant="plain">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="w-10 text-center text-xs">#</TableHead>
                  {EDITABLE_COLS.map((c) => (
                    <TableHead key={c.key} className={cn("text-xs font-semibold", c.w)}>
                      {c.label}
                    </TableHead>
                  ))}
                  {COMPUTED_COLS.map((c) => (
                    <TableHead
                      key={c.key}
                      className="min-w-[110px] bg-muted/60 text-xs font-semibold text-muted-foreground"
                    >
                      {c.label}
                    </TableHead>
                  ))}
                  <TableHead className="w-10 text-center"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {shownIndexes.map((i) => {
                  const r = rows[i]!;
                  const c = computed[i] ?? emptyComputed();
                  const blocked = issueSummary.blockRows.has(i);
                  const warned = issueSummary.warnRows.has(i);
                  const hint = step1FixHint(i, validationErrors, weightWarnings);
                  const specOptions = cartonSpecsBySku[r.sku] ?? [];
                  return (
                    <TableRow
                      key={i}
                      data-testid="step1-grid-row"
                      className={cn(
                        "hover:bg-transparent",
                        blocked && "bg-red-50",
                        !blocked && warned && "bg-amber-50",
                      )}
                    >
                      <TableCell className="text-center text-xs text-muted-foreground">
                        {i + 1}
                        {hint ? (
                          <div className="mt-1 text-[10px] leading-tight text-amber-800">{hint}</div>
                        ) : null}
                      </TableCell>
                      {EDITABLE_COLS.map((col) => (
                        <TableCell key={col.key} className="p-1">
                          {col.key === "sku" && (r.dataSource || specOptions.length > 1) ? (
                            <div className="flex min-w-[120px] flex-col gap-1">
                              <Input
                                value={r[col.key]}
                                onChange={(e) => update(i, col.key, e.target.value)}
                                className="h-8 border-transparent bg-transparent px-2 text-xs shadow-none focus-visible:border-input focus-visible:bg-background"
                              />
                              {specOptions.length > 1 ? (
                                <select
                                  data-testid="carton-spec-select"
                                  className="h-7 rounded border border-input bg-background px-1 text-[10px]"
                                  value={String(specOptions.find((spec) => String(spec.qty_per_carton) === r.perBox)?.id ?? specOptions[0].id)}
                                  onChange={(event) => {
                                    const chosen = specOptions.find((spec) => String(spec.id) === event.target.value);
                                    if (chosen) applySpec(i, chosen);
                                  }}
                                >
                                  {specOptions.map((spec) => (
                                    <option key={spec.id} value={spec.id}>
                                      {spec.spec_name}
                                    </option>
                                  ))}
                                </select>
                              ) : null}
                              {r.dataSource ? (
                                <Badge
                                  variant="outline"
                                  className={cn(
                                    "w-fit px-1.5 py-0 text-[10px] font-normal",
                                    r.dataSource === "official"
                                      ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                                      : "border-amber-300 bg-amber-50 text-amber-800",
                                  )}
                                >
                                  {r.dataSource === "official" ? "🟢 外箱主数据" : "🟡 手填外箱"}
                                </Badge>
                              ) : null}
                            </div>
                          ) : (
                            <Input
                              id={col.key === "unitKg" ? `step1-unit-kg-${i}` : undefined}
                              value={r[col.key]}
                              onChange={(e) => update(i, col.key, e.target.value)}
                              className="h-8 border-transparent bg-transparent px-2 text-xs shadow-none focus-visible:border-input focus-visible:bg-background"
                            />
                          )}
                        </TableCell>
                      ))}
                      {COMPUTED_COLS.map((col) => (
                        <TableCell
                          key={col.key}
                          className="bg-muted/40 px-3 py-2 font-mono text-xs text-foreground"
                        >
                          {c[col.key as keyof ComputedDisplay]}
                        </TableCell>
                      ))}
                      <TableCell className="p-1 text-center">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-muted-foreground transition-colors hover:bg-red-50 hover:text-red-600"
                          onClick={() => removeRow(i)}
                          title="删除该行"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableScrollArea>
          <div className="border-t border-border px-3 py-2">
            <Button variant="ghost" size="sm" onClick={addRow} className="h-7 gap-1 text-xs">
              <Plus className="h-3.5 w-3.5" />
              添加一行
            </Button>
          </div>
        </CardContent>
      </Card>

      <Step1CostDashboard
        data={
          costDashboard
            ? { ...costDashboard, actual_placement_fee: actualPlacementFee ?? undefined }
            : null
        }
        loading={previewLoading}
      />

      {weightWarnings.length > 0 && (
        <Alert className="border-amber-300 bg-amber-50 text-amber-950">
          <AlertTriangle className="h-4 w-4 !text-amber-600" />
          <AlertTitle className="text-sm font-semibold">单箱毛重与理论值不符</AlertTitle>
          <AlertDescription className="mt-1 text-xs">
            <ul className="list-inside list-disc space-y-1">
              {weightWarnings.map((w) => (
                <li key={`${w.row_index}-${w.sku}`}>
                  {w.message}
                  {(w.kind === "suspect_unit_in_gross" || w.kind === "unit_weight_missing") && (
                    <span className="ml-2 inline-flex gap-1">
                      <button
                        type="button"
                        className="underline"
                        onClick={() => document.getElementById(`step1-unit-kg-${w.row_index}`)?.focus()}
                      >
                        去填单个重量
                      </button>
                      <button
                        type="button"
                        className="underline"
                        onClick={() => {
                          setFixRow(w.row_index);
                          setFixUnit("");
                        }}
                      >
                        一键修正
                      </button>
                      <button type="button" className="underline" onClick={keepDeclaredWeights}>
                        保留录入值
                      </button>
                    </span>
                  )}
                  {w.requires_confirm && w.kind !== "suspect_unit_in_gross" && w.kind !== "unit_weight_missing" && (
                    <span className="ml-2 inline-flex gap-1">
                      <button
                        type="button"
                        className="underline"
                        onClick={useCalculatedWeights}
                        disabled={w.suggested_gross_kg == null}
                      >
                        使用计算值
                      </button>
                      <button type="button" className="underline" onClick={keepDeclaredWeights}>
                        保留录入值
                      </button>
                    </span>
                  )}
                </li>
              ))}
            </ul>
            {weightConfirmOpen && (
              <p className="mt-2 text-[11px] font-medium">这批录入的毛重还没确认。改动后会再要求确认一次。</p>
            )}
            <p className="mt-2 text-[11px] text-amber-800/90">
              单重缺失时不会把空箱重当成建议值。疑似单件重填进毛重时，阈值是内部经验值。内部阈值，非官方规定。导出前仍要确认。
            </p>
          </AlertDescription>
        </Alert>
      )}
      <ConfirmDialog
        open={fixRow != null}
        title="按单重重算毛重"
        description="输入单个重量后，单箱毛重改为 装量 × 单重 + 皮重。"
        confirmLabel="写入"
        onCancel={() => setFixRow(null)}
        onConfirm={() => {
          if (fixRow != null) applyUnitWeightFix(fixRow, fixUnit);
          setFixRow(null);
        }}
      >
        <Input
          autoFocus
          inputMode="decimal"
          placeholder="单个重量 kg"
          value={fixUnit}
          onChange={(e) => setFixUnit(e.target.value)}
        />
      </ConfirmDialog>

      {validationErrors.length > 0 && (
        <Alert className="border-red-200 bg-red-50 text-red-900">
          <AlertTriangle className="h-4 w-4 !text-red-600" />
          <AlertTitle className="text-sm font-semibold text-red-700">
            以下单元格需补全后才能进入下一步
          </AlertTitle>
          <AlertDescription className="mt-1 text-xs text-red-700/90">
            <ul className="list-inside list-disc space-y-0.5">
              {validationErrors.map((e, idx) => (
                <li key={`${e.row_index}-${e.field}-${idx}`}>
                  第 {e.row_number} 行：缺失 {e.field}
                </li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      <div data-bottom-bar className="fixed bottom-0 left-[var(--app-sidebar-width,340px)] right-0 z-10 border-t border-border bg-card/95 px-6 py-3 backdrop-blur supports-[backdrop-filter]:bg-card/80">
        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatBadge
              icon={<Package className="h-4 w-4" />}
              label="预计总整箱数"
              value={previewLoading ? "…" : String(totalFullBoxes)}
            />
            <StatBadge
              icon={<Scale className="h-4 w-4" />}
              label="预计总净重"
              value={previewLoading ? "…" : `${totalNet.toFixed(3)} kg`}
            />
            <StatBadge
              icon={<Scale className="h-4 w-4" />}
              label="预计总毛重"
              value={previewLoading ? "…" : `${totalGross.toFixed(3)} kg`}
            />
            <StatBadge
              icon={<Cuboid className="h-4 w-4" />}
              label="预计总方数 (CBM)"
              value={previewLoading ? "…" : totalCbm.toFixed(3)}
            />
            <StatBadge
              icon={<Weight className="h-4 w-4" />}
              label="预计总体积重"
              value={previewLoading ? "…" : `${totalVolWeight.toFixed(3)} kg`}
            />
            <StatBadge
              icon={<Package className="h-4 w-4" />}
              label="📦 平均密度"
              value={previewLoading ? "…" : `${cargoDensity.toFixed(3)} kg/CBM`}
            />
          </div>
          <Button
            size="lg"
            className="gap-2 px-8 text-base font-semibold shadow-md"
            disabled={validationErrors.length > 0 || previewLoading}
            onClick={() => {
              if (validationErrors.length === 0) onNext?.();
            }}
          >
            下一步
            <ArrowRight className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

function StatBadge({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-border bg-background px-3.5 py-2 shadow-sm">
      <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary/10 text-primary">
        {icon}
      </div>
      <div className="flex flex-col leading-tight">
        <span className="text-[10px] text-muted-foreground">{label}</span>
        <span className="text-sm font-semibold tabular-nums text-foreground">{value}</span>
      </div>
    </div>
  );
}
