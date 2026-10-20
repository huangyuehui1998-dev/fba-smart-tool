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
    parseAction,
    previewLoading,
    error,
    success,
    fileInputRef,
    excelInputId,
    totals: { totalFullBoxes, totalNet, totalGross },
    update,
    addRow,
    removeRow,
    handleParseLocal,
    handleParseDeepseek,
    handleExcelUpload,
    handleDownloadTemplate,
  } = useStep1Logic();

  return (
    <div className="space-y-6 pb-32">
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

      <Card className="shadow-sm">
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle className="text-base">可编辑数据网格</CardTitle>
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
                {rows.map((r, i) => {
                  const c = computed[i] ?? emptyComputed();
                  return (
                    <TableRow key={i} className="hover:bg-transparent">
                      <TableCell className="text-center text-xs text-muted-foreground">
                        {i + 1}
                      </TableCell>
                      {EDITABLE_COLS.map((col) => (
                        <TableCell key={col.key} className="p-1">
                          {col.key === "sku" && r.dataSource ? (
                            <div className="flex min-w-[120px] flex-col gap-1">
                              <Input
                                value={r[col.key]}
                                onChange={(e) => update(i, col.key, e.target.value)}
                                className="h-8 border-transparent bg-transparent px-2 text-xs shadow-none focus-visible:border-input focus-visible:bg-background"
                              />
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
                            </div>
                          ) : (
                            <Input
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
            <ul className="list-inside list-disc space-y-0.5">
              {weightWarnings.map((w) => (
                <li key={`${w.row_index}-${w.sku}`}>{w.message}</li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] text-amber-800/90">
              不阻断流程。但录入毛重会直接用于申报与货代计费，建议复磅后再继续。
            </p>
          </AlertDescription>
        </Alert>
      )}

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

      <div className="fixed bottom-0 left-[var(--app-sidebar-width,340px)] right-0 z-10 border-t border-border bg-card/95 px-6 py-3 backdrop-blur supports-[backdrop-filter]:bg-card/80">
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
