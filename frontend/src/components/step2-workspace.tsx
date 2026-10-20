import { Package, AlertTriangle, ArrowRight, ArrowLeft, Plus, Trash2, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { groupBoxItems } from "@/lib/box-editor";
import { useBoxValidation } from "@/hooks/use-box-validation";
import { useWorkflow } from "@/context/workflow-context";
import { StaleDataBanner } from "@/components/stale-data-banner";

export function Step2Workspace({ onPrev, onNext }: { onPrev?: () => void; onNext?: () => void }) {
  const { staleness } = useWorkflow();
  const {
    detail,
    metrics,
    tailPool,
    hasOverweight,
    weightLimitKg,
    initLoading,
    syncLoading,
    assignLoading,
    error,
    fbaCompliance,
    hasFbaBlock,
    pickSku,
    setPickSku,
    pickQty,
    setPickQty,
    pickBox,
    setPickBox,
    overweightCount,
    fbaGrossCount,
    sideWarningCount,
    cannotProceed,
    fullCount,
    mixCount,
    boxCount,
    addDetailRow,
    removeDetailRow,
    updateDetail,
    handleAssignTail,
    lockPlan,
    recalculateBoxes,
  } = useBoxValidation();

  return (
    <div className="space-y-6 pb-28">
      <StaleDataBanner
        step={2}
        staleness={staleness}
        onRefresh={() => void recalculateBoxes()}
        refreshLabel="重新排箱"
        loading={initLoading}
      />
      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle className="text-sm">操作失败</AlertTitle>
          <AlertDescription className="text-xs">{error}</AlertDescription>
        </Alert>
      )}

      {fbaCompliance &&
        (sideWarningCount > 0 ||
          fbaCompliance.gross_violation_count > 0 ||
          fbaCompliance.box_count_warning) && (
        <div className="space-y-2">
          {fbaCompliance.box_count_warning && (
            <Alert className="border-amber-300 bg-amber-50 text-amber-950">
              <AlertTriangle className="h-4 w-4 !text-amber-600" />
              <AlertTitle className="text-sm font-semibold">单票箱数超过亚马逊上限</AlertTitle>
              <AlertDescription className="mt-1 text-xs">
                {fbaCompliance.box_count_warning.message}
                <p className="mt-2 text-[11px] text-amber-800/90">
                  超出部分不会被丢弃，但 Send to Amazon 需按货件拆分后分批上传。
                </p>
              </AlertDescription>
            </Alert>
          )}
          {sideWarningCount > 0 && (
            <Alert className="border-amber-300 bg-amber-50 text-amber-950">
              <AlertTriangle className="h-4 w-4 !text-amber-600" />
              <AlertTitle className="text-sm font-semibold">FBA 外箱超边警示</AlertTitle>
              <AlertDescription className="mt-1 text-xs">
                <ul className="list-inside list-disc space-y-0.5">
                  {fbaCompliance.carton_side_warnings.map((w) => (
                    <li key={w.sku}>{w.message}</li>
                  ))}
                </ul>
                <p className="mt-2 text-[11px] text-amber-800/90">
                  单边不得超过 {fbaCompliance.limits.max_side_cm} cm ({fbaCompliance.limits.max_side_in} in)
                </p>
              </AlertDescription>
            </Alert>
          )}
          {fbaCompliance.gross_violation_count > 0 && (
            <Alert variant="destructive">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle className="text-sm">FBA 单箱毛重红线 — 禁止进入下一步</AlertTitle>
              <AlertDescription className="mt-1 text-xs">
                <ul className="list-inside list-disc space-y-0.5">
                  {fbaCompliance.box_gross_violations.map((v) => (
                    <li key={v.box_no}>{v.message}</li>
                  ))}
                </ul>
                <p className="mt-2 text-[11px] opacity-90">
                  标准件单箱毛重上限 {fbaCompliance.limits.max_standard_gross_kg} kg (
                  {fbaCompliance.limits.max_standard_gross_lb} lbs)。仅「单箱 1 件超大件」可豁免。
                </p>
              </AlertDescription>
            </Alert>
          )}
        </div>
      )}

      {initLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在生成初始装箱方案…
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base">待排尾数池</CardTitle>
              <p className="text-xs text-muted-foreground">
                人工凑箱：在右侧表格修改箱号/数量，系统将自动从此池扣减。
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              <TableScrollArea maxHeight="min(40vh, 16rem)">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableHead className="h-8 text-[11px]">SKU简称</TableHead>
                      <TableHead className="h-8 text-right text-[11px]">待排尾数</TableHead>
                      <TableHead className="h-8 text-right text-[11px]">单重(kg)</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tailPool.length === 0 ? (
                      <TableRow>
                        <TableCell
                          colSpan={3}
                          className="py-4 text-center text-xs text-muted-foreground"
                        >
                          {syncLoading ? "更新中…" : "尾数已全部分配"}
                        </TableCell>
                      </TableRow>
                    ) : (
                      tailPool.map((p) => (
                        <TableRow key={p.SKU简称}>
                          <TableCell className="py-1.5 font-mono text-xs">{p.SKU简称}</TableCell>
                          <TableCell className="py-1.5 text-right text-xs font-semibold tabular-nums">
                            {p.待排尾数}
                          </TableCell>
                          <TableCell className="py-1.5 text-right font-mono text-xs">
                            {Number(p["单个重量(kg)"]).toFixed(2)}
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </TableScrollArea>

              <div className="space-y-3 rounded-md border border-border bg-muted/30 p-3">
                <h4 className="text-xs font-semibold text-foreground">快速分配尾数</h4>
                <div className="space-y-1.5">
                  <Label className="text-[11px]">SKU</Label>
                  <Select value={pickSku} onValueChange={setPickSku} disabled={!tailPool.length}>
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue placeholder="选择 SKU..." />
                    </SelectTrigger>
                    <SelectContent>
                      {tailPool.map((p) => (
                        <SelectItem key={p.SKU简称} value={p.SKU简称}>
                          {p.SKU简称} (余 {p.待排尾数})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="space-y-1.5">
                    <Label className="text-[11px]">数量</Label>
                    <Input
                      type="number"
                      min={1}
                      max={Math.max(1, Number(tailPool.find((p) => p.SKU简称 === pickSku)?.待排尾数 ?? 1))}
                      value={pickQty}
                      onChange={(e) => {
                        const left = Number(tailPool.find((p) => p.SKU简称 === pickSku)?.待排尾数 ?? 0);
                        const v = Math.floor(Number(e.target.value) || 1);
                        setPickQty(left > 0 ? Math.min(Math.max(1, v), left) : Math.max(1, v));
                      }}
                      className="h-8 text-xs"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-[11px]">目标箱号</Label>
                    <Input
                      type="number"
                      min={1}
                      value={pickBox}
                      onChange={(e) => setPickBox(Number(e.target.value) || 1)}
                      className="h-8 text-xs"
                    />
                  </div>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  className="w-full"
                  disabled={assignLoading || !tailPool.length}
                  onClick={() => void handleAssignTail()}
                >
                  {assignLoading ? (
                    <>
                      <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      分配中…
                    </>
                  ) : (
                    "添加到目标箱"
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="lg:col-span-8">
          <Tabs defaultValue="visual" className="space-y-4">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="visual">实体纸箱视图（可视化）</TabsTrigger>
              <TabsTrigger value="table">排箱明细（表格）</TabsTrigger>
            </TabsList>

            <TabsContent value="visual" className="space-y-4">
              <Card className="shadow-sm">
                <CardContent className="p-0">
                  <TableScrollArea variant="plain">
                    <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/40 hover:bg-muted/40">
                        <TableHead className="h-9 text-xs">箱指标汇总</TableHead>
                        <TableHead className="h-9 text-right text-xs">总箱数</TableHead>
                        <TableHead className="h-9 text-right text-xs">整箱行</TableHead>
                        <TableHead className="h-9 text-right text-xs">混装行</TableHead>
                        <TableHead className="h-9 text-right text-xs">超重</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      <TableRow>
                        <TableCell className="py-2 text-xs text-muted-foreground">
                          本次方案 {syncLoading && "· 同步中…"}
                        </TableCell>
                        <TableCell className="py-2 text-right font-mono text-sm font-semibold tabular-nums">
                          {boxCount}
                        </TableCell>
                        <TableCell className="py-2 text-right font-mono text-sm tabular-nums">
                          {fullCount}
                        </TableCell>
                        <TableCell className="py-2 text-right font-mono text-sm tabular-nums">
                          {mixCount}
                        </TableCell>
                        <TableCell className="py-2 text-right">
                          <span
                            className={cn(
                              "font-mono text-sm font-semibold tabular-nums",
                              overweightCount > 0 ? "text-red-600" : "text-emerald-600",
                            )}
                          >
                            {overweightCount}
                          </span>
                        </TableCell>
                      </TableRow>
                    </TableBody>
                    </Table>
                  </TableScrollArea>
                </CardContent>
              </Card>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {metrics.map((m) => {
                  const boxNo = Number(m.箱号);
                  const items = groupBoxItems(detail, boxNo);
                  const source =
                    items.length <= 1 && detail.find((d) => d.box === boxNo)?.source === "整箱"
                      ? "整箱"
                      : "混装";
                  return (
                    <CartonCard
                      key={boxNo}
                      boxNo={boxNo}
                      type={source as "整箱" | "混装"}
                      items={items}
                      grossKg={Number(m["毛重(kg)"])}
                      overweight={Boolean(m.超重)}
                      fbaGrossViolation={Boolean(m.FBA毛重违规)}
                      fbaOversizeExempt={Boolean(m.FBA超大件豁免)}
                      weightLimit={weightLimitKg}
                    />
                  );
                })}
                {!metrics.length && !initLoading && (
                  <p className="col-span-full text-center text-sm text-muted-foreground">
                    暂无装箱数据
                  </p>
                )}
              </div>
            </TabsContent>

            <TabsContent value="table">
              <Card className="shadow-sm">
                <CardContent className="p-0">
                  <TableScrollArea variant="plain">
                    <Table>
                      <TableHeader>
                        <TableRow className="bg-muted/40 hover:bg-muted/40">
                          <TableHead className="h-9 w-16 text-xs">箱号</TableHead>
                          <TableHead className="h-9 w-24 text-xs">来源</TableHead>
                          <TableHead className="h-9 text-xs">SKU简称</TableHead>
                          <TableHead className="h-9 w-24 text-xs">数量</TableHead>
                          <TableHead className="h-9 w-12" />
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {detail.map((r) => (
                          <TableRow key={r.id} className="hover:bg-transparent">
                            <TableCell className="bg-muted/30 p-1">
                              <Input
                                type="number"
                                value={r.box}
                                onChange={(e) => updateDetail(r.id, "box", e.target.value)}
                                className="h-8 text-center text-xs"
                              />
                            </TableCell>
                            <TableCell className="p-1">
                              <Select
                                value={r.source}
                                onValueChange={(v) => updateDetail(r.id, "source", v)}
                              >
                                <SelectTrigger className="h-8 text-xs">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="整箱">整箱</SelectItem>
                                  <SelectItem value="混装">混装</SelectItem>
                                </SelectContent>
                              </Select>
                            </TableCell>
                            <TableCell className="p-1">
                              <Input
                                value={r.sku}
                                onChange={(e) => updateDetail(r.id, "sku", e.target.value)}
                                className="h-8 text-xs"
                              />
                            </TableCell>
                            <TableCell className="p-1">
                              <Input
                                type="number"
                                value={r.qty}
                                onChange={(e) => updateDetail(r.id, "qty", e.target.value)}
                                className="h-8 text-xs"
                              />
                            </TableCell>
                            <TableCell className="p-1 text-center">
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => removeDetailRow(r.id)}
                                className="h-7 w-7 text-muted-foreground hover:text-destructive"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableScrollArea>
                  <div className="border-t border-border px-3 py-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={addDetailRow}
                      className="h-7 gap-1 text-xs"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      添加一行
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {metrics.length > 0 && (
                <Card className="mt-4 shadow-sm">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">每箱指标</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    <TableScrollArea variant="plain">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            {["箱号", "SKU种类", "件数", "净重(kg)", "毛重(kg)", "超重", "FBA违规"].map(
                              (h) => (
                                <TableHead key={h} className="text-xs">
                                  {h}
                                </TableHead>
                              ),
                            )}
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {metrics.map((m) => (
                            <TableRow key={m.箱号}>
                              <TableCell className="font-mono text-xs">{m.箱号}</TableCell>
                              <TableCell className="text-xs">{m.SKU种类}</TableCell>
                              <TableCell className="text-xs">{m.件数}</TableCell>
                              <TableCell className="font-mono text-xs">{m["净重(kg)"]}</TableCell>
                              <TableCell className="font-mono text-xs">{m["毛重(kg)"]}</TableCell>
                              <TableCell className="text-xs">{m.超重 ? "是" : "否"}</TableCell>
                              <TableCell className={cn("text-xs", m.FBA毛重违规 && "font-semibold text-red-600")}>
                                {m.FBA毛重违规 ? "毛重红线" : m.FBA超大件豁免 ? "超大件豁免" : "—"}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </TableScrollArea>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          </Tabs>
        </div>
      </div>

      <div className="fixed bottom-0 left-[var(--app-sidebar-width,340px)] right-0 z-10 border-t border-border bg-card/95 px-6 py-3 backdrop-blur supports-[backdrop-filter]:bg-card/80">
        <div className="flex items-center justify-between gap-4">
          <Button variant="outline" size="lg" onClick={onPrev} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            上一步
          </Button>
          <div className="flex items-center gap-3">
            {(hasOverweight || overweightCount > 0 || hasFbaBlock || fbaGrossCount > 0) && (
              <span className="flex items-center gap-1.5 text-xs font-medium text-red-600">
                <AlertTriangle className="h-3.5 w-3.5" />
                {hasFbaBlock || fbaGrossCount > 0
                  ? `FBA 毛重红线：${fbaGrossCount} 箱超标，需调整`
                  : `存在 ${overweightCount} 个超重箱，需先调整`}
              </span>
            )}
            <Button
              size="lg"
              disabled={cannotProceed}
              className="gap-2 px-8 text-base font-semibold shadow-md"
              onClick={() => {
                lockPlan();
                onNext?.();
              }}
            >
              确认锁定方案并下一步
              <ArrowRight className="h-5 w-5" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function CartonCard({
  boxNo,
  type,
  items,
  grossKg,
  overweight,
  fbaGrossViolation,
  fbaOversizeExempt,
  weightLimit,
}: {
  boxNo: number;
  type: "整箱" | "混装";
  items: { sku: string; qty: number }[];
  grossKg: number;
  overweight: boolean;
  fbaGrossViolation?: boolean;
  fbaOversizeExempt?: boolean;
  weightLimit: number;
}) {
  const highlight = overweight || fbaGrossViolation;
  const pct = Math.min(100, (grossKg / weightLimit) * 100);

  return (
    <div
      className={cn(
        "relative rounded-lg border bg-card p-3 shadow-sm transition-shadow hover:shadow-md",
        highlight ? "border-2 border-red-500" : "border-border",
      )}
    >
      {fbaGrossViolation && (
        <span className="absolute -right-1.5 -top-1.5 flex h-6 items-center gap-1 rounded-full bg-red-600 px-2 text-[10px] font-bold text-white shadow-md">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />
          FBA 毛重红线
        </span>
      )}
      {!fbaGrossViolation && overweight && (
        <span className="absolute -right-1.5 -top-1.5 flex h-6 items-center gap-1 rounded-full bg-red-600 px-2 text-[10px] font-bold text-white shadow-md">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" />
          超重！
        </span>
      )}
      {fbaOversizeExempt && grossKg > weightLimit && (
        <Badge variant="outline" className="absolute -right-1.5 -top-1.5 border-violet-300 bg-violet-50 text-[10px] text-violet-800">
          超大件豁免
        </Badge>
      )}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-sm font-semibold">
          <Package className="h-4 w-4 text-muted-foreground" />
          箱号: {boxNo}
        </div>
        <Badge
          variant="secondary"
          className={cn(
            "text-[10px]",
            type === "整箱"
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-blue-200 bg-blue-50 text-blue-700",
          )}
        >
          {type}
        </Badge>
      </div>
      <ul className="mt-3 space-y-1 border-t border-border pt-2">
        {items.map((it, i) => (
          <li key={i} className="flex items-center justify-between text-xs">
            <span className="font-mono text-foreground">{it.sku}</span>
            <span className="font-mono text-muted-foreground">× {it.qty}</span>
          </li>
        ))}
      </ul>
      <div className="mt-3 space-y-1">
        <div className="flex items-center justify-between text-[10px]">
          <span className="text-muted-foreground">毛重</span>
          <span
            className={cn(
              "font-mono font-semibold tabular-nums",
              overweight ? "text-red-600" : "text-foreground",
            )}
          >
            {grossKg.toFixed(1)}kg / {weightLimit}kg
          </span>
        </div>
        <Progress value={pct} className={cn("h-1.5", overweight && "[&>div]:bg-red-500")} />
      </div>
    </div>
  );
}
