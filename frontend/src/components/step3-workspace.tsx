import {
  CheckCircle2,
  Download,
  ArrowLeft,
  ArrowRight,
  Loader2,
  AlertTriangle,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { matrixBoxColumns } from "@/lib/box-editor";
import { useStep3Export } from "@/hooks/use-step3-export";
import { TableScrollArea } from "@/components/table-scroll-area";
import { useWorkflow } from "@/context/workflow-context";
import { StaleDataBanner } from "@/components/stale-data-banner";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TRANSPORT_MODES, type TransportMode } from "@/lib/transport-mode";

function MatrixTable({ matrix }: { matrix: Record<string, unknown>[] }) {
  const boxCols = matrixBoxColumns(matrix);
  if (!matrix.length) {
    return (
      <p className="rounded-lg border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
        暂无矩阵数据
      </p>
    );
  }

  return (
    <TableScrollArea>
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="bg-muted/60">
            <th className="sticky left-0 z-10 min-w-[180px] border-b border-r border-border bg-muted/80 px-3 py-2 text-left text-[11px] font-semibold backdrop-blur">
              SKU简称
            </th>
            {boxCols.map((col) => (
              <th
                key={col}
                className="min-w-[64px] border-b border-border px-2 py-2 text-center text-[11px] font-semibold"
              >
                {col}
              </th>
            ))}
            <th className="min-w-[80px] border-b border-l border-border bg-muted/80 px-3 py-2 text-right text-[11px] font-semibold">
              合计
            </th>
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, si) => {
            const sku = String(row["SKU简称"] ?? "");
            const vals = boxCols.map((col) => {
              const v = row[col];
              return v === null || v === undefined || v === "" ? 0 : Number(v);
            });
            const total = vals.reduce((a, b) => a + b, 0);
            return (
              <tr key={`${sku}-${si}`} className="border-b border-border hover:bg-muted/20">
                <td className="sticky left-0 z-10 border-r border-border bg-card px-3 py-2 font-mono text-xs font-semibold">
                  {sku}
                </td>
                {vals.map((v, bi) => (
                  <td
                    key={bi}
                    className={cn(
                      "px-2 py-2 text-center font-mono tabular-nums",
                      v === 0 ? "text-muted-foreground/40" : "text-foreground",
                    )}
                  >
                    {v || ""}
                  </td>
                ))}
                <td className="border-l border-border bg-muted/30 px-3 py-2 text-right font-mono text-xs font-semibold tabular-nums">
                  {total}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </TableScrollArea>
  );
}

export function Step3Workspace({ onPrev, onNext }: { onPrev?: () => void; onNext?: () => void }) {
  const { staleness, transportMode, setTransportMode } = useWorkflow();
  const {
    boxLocked,
    loading,
    downloading,
    error,
    step3Matrix,
    step3BoxCount,
    step3SkuCount,
    totalGross,
    downloadInternal,
    downloadAmazon,
    refreshPreview,
  } = useStep3Export();

  const exportBlocked = !boxLocked || Boolean(staleness.export);

  if (!boxLocked && !step3Matrix.length) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle>方案未锁定</AlertTitle>
        <AlertDescription>请先在 Step 2 锁定装箱方案。</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-5 pb-28">
      <StaleDataBanner
        step={3}
        staleness={staleness}
        onRefresh={() => void refreshPreview()}
        refreshLabel="重新生成预览"
        loading={loading}
      />
      {!boxLocked && step3Matrix.length > 0 && (
        <Alert className="border-amber-300 bg-amber-50 text-amber-950">
          <AlertTriangle className="h-4 w-4 !text-amber-600" />
          <AlertTitle className="text-sm font-semibold">方案已解锁（可对照上一版）</AlertTitle>
          <AlertDescription className="text-xs">
            Step 1 发货数据已变更。下方为上一版导出预览，不能作为正式文件下载。请回 Step 2 重新排箱并锁定。
          </AlertDescription>
        </Alert>
      )}
      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex max-w-sm flex-col gap-1.5">
        <Label htmlFor="transport-mode">运输方式</Label>
        <Select
          value={transportMode}
          onValueChange={(value) => setTransportMode(value as TransportMode)}
        >
          <SelectTrigger id="transport-mode" className="bg-card">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TRANSPORT_MODES.map((mode) => (
              <SelectItem key={mode.value} value={mode.value}>
                {mode.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-[11px] text-muted-foreground">
          默认 SPD-合作承运人。箱数上限按所选方式检查，并随任务快照保存。
        </p>
      </div>

      {boxLocked && !staleness.export && (
        <Alert className="border-emerald-200 bg-emerald-50">
          <CheckCircle2 className="h-4 w-4 !text-emerald-600" />
          <AlertTitle className="text-sm font-semibold text-emerald-800">方案已锁定</AlertTitle>
          <AlertDescription className="text-xs text-emerald-700/90">
            当前装箱方案：共 <span className="font-semibold">{step3SkuCount || "—"} 个 SKU</span> ·
            分配至 <span className="font-semibold">{step3BoxCount || "—"} 个纸箱</span>
            {totalGross > 0 && (
              <>
                {" "}
                · 总毛重 <span className="font-semibold">{totalGross.toFixed(2)} kg</span>
              </>
            )}
          </AlertDescription>
        </Alert>
      )}

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" />
          正在生成预览矩阵…
        </div>
      ) : (
        <Tabs defaultValue="internal" className="space-y-3">
          <TabsList className="grid w-full max-w-xl grid-cols-2">
            <TabsTrigger value="internal">内部留档预览（{step3BoxCount} 箱）</TabsTrigger>
            <TabsTrigger value="amazon">Send to Amazon 预览（{step3BoxCount} 箱）</TabsTrigger>
          </TabsList>
          <TabsContent value="internal">
            <MatrixTable matrix={step3Matrix} />
          </TabsContent>
          <TabsContent value="amazon">
            <p className="mb-2 text-xs text-muted-foreground">
              导出时将自动转换为 in / lb；下方矩阵为装箱数量分布预览。
            </p>
            <MatrixTable matrix={step3Matrix} />
          </TabsContent>
        </Tabs>
      )}

      <Card className="border-primary/20 bg-primary/[0.03] shadow-sm">
        <CardContent className="flex flex-col items-center gap-3 py-6">
          <div className="text-center">
            <h3 className="text-sm font-semibold text-foreground">导出报表文件</h3>
            <p className="mt-1 text-xs text-muted-foreground">
              {exportBlocked
                ? "结果已过期或方案未锁定，不能下载正式文件。"
                : "内部表用于工厂/货代留档；Send to Amazon 模板可直接上传至卖家中心。"}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button
              size="lg"
              variant="outline"
              className="gap-2"
              disabled={!!downloading || exportBlocked}
              title={exportBlocked ? "结果已过期，不能作为正式文件下载" : undefined}
              onClick={() => void downloadInternal()}
            >
              {downloading === "internal" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              下载内部表 (.xlsx)
            </Button>
            <Button
              size="lg"
              className="gap-2 shadow-md"
              disabled={!!downloading || exportBlocked}
              title={exportBlocked ? "结果已过期，不能作为正式文件下载" : undefined}
              onClick={() => void downloadAmazon()}
            >
              {downloading === "amazon" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              下载 Send to Amazon 模板 (.xlsx)
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="fixed bottom-0 left-[var(--app-sidebar-width,340px)] right-0 z-10 border-t border-border bg-card/95 px-6 py-3 backdrop-blur supports-[backdrop-filter]:bg-card/80">
        <div className="flex items-center justify-between gap-4">
          <Button variant="outline" size="lg" onClick={onPrev} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            上一步
          </Button>
          <Button
            size="lg"
            onClick={onNext}
            className="gap-2 px-8 text-base font-semibold shadow-md"
          >
            进入 Step 4: 回传校验
            <ArrowRight className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </div>
  );
}
