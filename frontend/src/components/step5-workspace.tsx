import { ArrowLeft, Download, Loader2, RefreshCw } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCustoms } from "@/hooks/use-customs";
import { useWorkflow } from "@/context/workflow-context";
import { StaleDataBanner } from "@/components/stale-data-banner";
import { Step5DeclaredValue } from "@/components/step5-declared-value";
import { cn } from "@/lib/utils";

function FieldRow({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string | number;
  onChange?: (v: string) => void;
  type?: string;
}) {
  return (
    <div className="grid grid-cols-[120px_1fr] items-center gap-2 text-sm">
      <Label className="text-muted-foreground">{label}</Label>
      {onChange ? (
        <Input type={type} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <span>{value}</span>
      )}
    </div>
  );
}

export function Step5Workspace({ onPrev }: { onPrev?: () => void }) {
  const { staleness } = useWorkflow();
  const {
    step4Ok,
    source,
    setSource,
    exporters,
    exporterId,
    setExporterId,
    orderNo,
    setOrderNo,
    shipmentOptions,
    selectedIds,
    toggleShipment,
    selectAllShipments,
    clearShipments,
    allSelected,
    isStale,
    data,
    loading,
    exporting,
    exportFormat,
    setExportFormat,
    error,
    canPreview,
    runPreview,
    runExport,
    patchData,
    patchLine,
    patchDate,
    activeTab,
    setActiveTab,
    hasInvoiceDraft,
    avgUnitPrice,
  } = useCustoms();

  if (!step4Ok && !shipmentOptions.length) {
    return (
      <div className="flex h-full min-h-[60vh] flex-col items-center justify-center gap-3 p-6">
        <p className="text-sm text-muted-foreground">请先完成 Step 4 货件校验并通过后再进入报关资料。</p>
        {onPrev && (
          <Button variant="outline" onClick={onPrev}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回 Step 4
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-4 p-6 pb-24">
      <StaleDataBanner step={5} staleness={staleness} />
      <Step5DeclaredValue data={data} onPatch={patchData} />
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1.5">
          <Label>出口商</Label>
          <Select value={exporterId} onValueChange={setExporterId}>
            <SelectTrigger className="w-[280px]">
              <SelectValue placeholder="选择出口商" />
            </SelectTrigger>
            <SelectContent>
              {exporters.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.name}
                  {p.is_active ? "（默认）" : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>订单号 / 合同号</Label>
          <Input
            className="w-[200px]"
            placeholder="如 DEMO-ORDER-001"
            value={orderNo}
            onChange={(e) => setOrderNo(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label>数据来源</Label>
          <div className="flex rounded-md border border-border p-0.5">
            <Button
              type="button"
              size="sm"
              variant={source === "invoice" ? "default" : "ghost"}
              className="rounded-sm"
              disabled={!hasInvoiceDraft}
              onClick={() => setSource("invoice")}
            >
              A · 发票明细
            </Button>
            <Button
              type="button"
              size="sm"
              variant={source === "shipment" ? "default" : "ghost"}
              className="rounded-sm"
              onClick={() => setSource("shipment")}
            >
              B · 发货重算
            </Button>
          </div>
          {!hasInvoiceDraft && (
            <p className="text-[11px] text-muted-foreground">
              尚未生成发票草稿，已自动使用 B · 发货重算
            </p>
          )}
        </div>
        <Button onClick={runPreview} disabled={!canPreview || loading}>
          {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
          生成预览
        </Button>
      </div>

      {shipmentOptions.length > 0 && (
        <div className="space-y-2 rounded-md border border-border bg-muted/30 p-3">
          <div className="flex items-center justify-between gap-2">
            <Label className="text-sm">
              本次报关货件
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                已选 {selectedIds.length}/{shipmentOptions.length} · 改动后需重新生成预览
              </span>
            </Label>
            <div className="flex shrink-0 gap-1">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs"
                disabled={allSelected}
                onClick={selectAllShipments}
              >
                全选
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs"
                disabled={selectedIds.length === 0}
                onClick={clearShipments}
              >
                清空
              </Button>
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground/80">
            单选=分票 · 多选=合并报关（相同 SKU 自动叠加）
          </p>
          {source === "invoice" &&
            selectedIds.length > 0 &&
            selectedIds.length < shipmentOptions.length && (
              <p className="text-xs text-muted-foreground">
                来源 A 仅含已生成发票的货件；分票建议用 B · 发货重算
              </p>
            )}
          <div className="flex flex-wrap gap-2">
            {shipmentOptions.map((s) => {
              const active = selectedIds.includes(s.id);
              return (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => toggleShipment(s.id)}
                  aria-pressed={active}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors",
                    active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-background text-muted-foreground hover:bg-muted",
                  )}
                >
                  <span
                    className={cn(
                      "flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border text-[9px] leading-none",
                      active ? "border-primary-foreground bg-primary-foreground/20" : "border-muted-foreground/50",
                    )}
                  >
                    {active ? "✓" : ""}
                  </span>
                  <span className="font-mono">{s.id}</span>
                  {s.warehouse && <span className="opacity-70">({s.warehouse})</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {data && (data.warnings ?? []).length > 0 && (
        <Alert
          variant={(data.blocking ?? []).length > 0 ? "destructive" : "default"}
          className={(data.blocking ?? []).length > 0 ? undefined : "border-amber-500/50 bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200"}
        >
          <AlertDescription>
            {(data.warnings ?? []).map((w) => (
              <div key={w.code}>{w.message}</div>
            ))}
          </AlertDescription>
        </Alert>
      )}

      {data && (data.price_sources ?? []).length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <span>申报价来源：</span>
          {(data.price_sources ?? []).map((p) => (
            <Badge key={p.sku} variant={p.source === "none" || p.source === "legacy" ? "destructive" : "outline"}>
              {p.sku} · {p.price ?? "无"} · {p.source_label}
            </Badge>
          ))}
        </div>
      )}

      {isStale && data && (
        <Alert className="border-amber-500/50 bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <AlertDescription>货件选择已变更，请重新点击「生成预览」</AlertDescription>
        </Alert>
      )}

      {!data ? (
        <Card className="border-dashed">
          <CardContent className="flex min-h-[320px] items-center justify-center text-sm text-muted-foreground">
            填写订单号并点击「生成预览」，可编辑后导出 .xlsx 报关资料包。
          </CardContent>
        </Card>
      ) : (
        <>
        {data && (
          <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-muted/30 px-4 py-2.5 text-sm">
            <span>
              总数量: <strong className="tabular-nums">{data.total_qty}</strong>
            </span>
            <span className="text-muted-foreground">|</span>
            <span>
              总金额: <strong className="tabular-nums">${data.total_amount}</strong>
            </span>
            <span className="text-muted-foreground">|</span>
            <span>
              平均单价: <strong className="tabular-nums">${avgUnitPrice.toFixed(2)}</strong>
              <span className="ml-1 text-xs text-muted-foreground">(总金额÷总数量)</span>
            </span>
          </div>
        )}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1">
          <TabsList className="flex h-auto flex-wrap gap-1">
            <TabsTrigger value="declaration">报关单</TabsTrigger>
            <TabsTrigger value="elements">申报要素</TabsTrigger>
            <TabsTrigger value="invoice">发票</TabsTrigger>
            <TabsTrigger value="packing">箱单</TabsTrigger>
            <TabsTrigger value="contract">合同</TabsTrigger>
            <TabsTrigger value="entrust">委托书</TabsTrigger>
          </TabsList>

          <TabsContent value="declaration" className="mt-4 space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">报关单头信息</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-2 md:grid-cols-2">
                <FieldRow label="合同号" value={data.order_no} onChange={(v) => patchData({ order_no: v })} />
                <FieldRow
                  label="出口日期"
                  value={data.dates.export_date ?? ""}
                  onChange={(v) => patchDate("export_date", v)}
                />
                <FieldRow
                  label="件数"
                  value={data.total_pieces}
                  onChange={(v) => patchData({ total_pieces: Number(v) || 0 })}
                  type="number"
                />
                <FieldRow
                  label="毛重(kg)"
                  value={data.total_gross_kg}
                  onChange={(v) => patchData({ total_gross_kg: Number(v) || 0 })}
                  type="number"
                />
                <FieldRow
                  label="净重(kg)"
                  value={data.total_net_kg}
                  onChange={(v) => patchData({ total_net_kg: Number(v) || 0 })}
                  type="number"
                />
                <FieldRow label="备注" value={data.remarks} onChange={(v) => patchData({ remarks: v })} />
              </CardContent>
            </Card>
            <LinesTable data={data} onPatchLine={patchLine} cols={["chinese_name", "hs_code", "qty", "unit_price", "amount", "net_kg"]} />
          </TabsContent>

          <TabsContent value="elements" className="mt-4">
            <LinesTable
              data={data}
              onPatchLine={patchLine}
              cols={["chinese_name", "hs_code", "brand", "model", "declare_elements"]}
            />
          </TabsContent>

          <TabsContent value="invoice" className="mt-4 space-y-4">
            <Card>
              <CardContent className="grid gap-2 pt-4 md:grid-cols-2">
                <FieldRow label="发票号" value={data.order_no} onChange={(v) => patchData({ order_no: v })} />
                <FieldRow
                  label="发票日期"
                  value={data.dates.invoice_date ?? ""}
                  onChange={(v) => patchDate("invoice_date", v)}
                />
                <FieldRow label="成交方式" value={data.trade_term} onChange={(v) => patchData({ trade_term: v })} />
                <FieldRow label="合计金额" value={data.total_amount} type="number" />
              </CardContent>
            </Card>
            <LinesTable data={data} onPatchLine={patchLine} cols={["chinese_name", "qty", "unit", "unit_price", "amount", "price_source"]} />
          </TabsContent>

          <TabsContent value="packing" className="mt-4 space-y-4">
            <Card>
              <CardContent className="grid gap-2 pt-4 md:grid-cols-2">
                <FieldRow
                  label="箱单日期"
                  value={data.dates.packing_date ?? ""}
                  onChange={(v) => patchDate("packing_date", v)}
                />
                <FieldRow label="目的国" value={data.dest_country ?? "美国"} onChange={(v) => patchData({ dest_country: v })} />
              </CardContent>
            </Card>
            <LinesTable data={data} onPatchLine={patchLine} cols={["chinese_name", "box_count", "qty", "gross_kg", "net_kg"]} />
          </TabsContent>

          <TabsContent value="contract" className="mt-4 space-y-4">
            <Card>
              <CardContent className="grid gap-2 pt-4 md:grid-cols-2">
                <FieldRow
                  label="合同日期"
                  value={data.dates.contract_date ?? ""}
                  onChange={(v) => patchDate("contract_date", v)}
                />
                <FieldRow
                  label="装运期"
                  value={data.dates.shipment_deadline ?? ""}
                  onChange={(v) => patchDate("shipment_deadline", v)}
                />
                <FieldRow
                  label="金额大写"
                  value={data.amount_in_words}
                  onChange={(v) => patchData({ amount_in_words: v })}
                />
              </CardContent>
            </Card>
            <LinesTable data={data} onPatchLine={patchLine} cols={["chinese_name", "qty", "unit", "unit_price", "amount"]} />
          </TabsContent>

          <TabsContent value="entrust" className="mt-4">
            <Card>
              <CardContent className="grid gap-2 pt-4 md:grid-cols-2">
                <FieldRow label="编号" value={data.order_no} />
                <FieldRow label="主要货物" value={data.main_goods_name} />
                <FieldRow label="HS编码" value={data.hs_codes_summary} />
                <FieldRow label="货物总价" value={data.total_amount} type="number" />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
        </>
      )}

      <div className="fixed bottom-0 left-[var(--app-sidebar-width,340px)] right-0 z-10 border-t border-border bg-card/95 px-6 py-3 backdrop-blur supports-[backdrop-filter]:bg-card/80">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            {onPrev && (
              <Button variant="outline" onClick={onPrev}>
                <ArrowLeft className="mr-2 h-4 w-4" />
                上一步
              </Button>
            )}
            {data && (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge variant="secondary">
                  {data.lines.length} 项 · 总数量 {data.total_qty} · 总金额 ${data.total_amount}
                </Badge>
                <Badge variant="outline">
                  平均单价 ${avgUnitPrice.toFixed(2)}
                </Badge>
              </div>
            )}
          </div>
          {data && (
            <label className="flex items-center gap-1 text-sm">
              报关方式
              <select
                className="rounded border px-2 py-1"
                value={data.declare_mode ?? ""}
                onChange={(e) => patchData({ declare_mode: e.target.value })}
              >
                <option value="单独">单独报关</option>
                <option value="合并">合并报关</option>
              </select>
            </label>
          )}
          <label className="flex items-center gap-1 text-sm">
            格式
            <select
              className="rounded border px-2 py-1"
              value={exportFormat}
              onChange={(e) => setExportFormat(e.target.value as "xlsx" | "xls")}
            >
              <option value="xlsx">.xlsx</option>
              <option value="xls">.xls</option>
            </select>
          </label>
          <Button
            onClick={runExport}
            disabled={!data || exporting || isStale || staleness.customs || staleness.validation}
            title={
              staleness.customs || staleness.validation
                ? "结果已过期，不能作为正式文件下载"
                : undefined
            }
          >
            {exporting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
            生成报关资料 (.{exportFormat})
          </Button>
        </div>
      </div>
    </div>
  );
}

const COL_LABELS: Record<string, string> = {
  chinese_name: "品名",
  hs_code: "HS编码",
  qty: "数量",
  unit: "单位",
  unit_price: "单价",
  amount: "金额",
  brand: "品牌",
  model: "型号",
  declare_elements: "申报要素",
  box_count: "箱数",
  gross_kg: "毛重",
  net_kg: "净重",
  price_source: "申报价来源",
};

function LinesTable({
  data,
  onPatchLine,
  cols,
}: {
  data: { lines: ReadonlyArray<object> };
  onPatchLine: (seq: number, patch: Record<string, unknown>) => void;
  cols: string[];
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-left">
            <th className="px-3 py-2">项号</th>
            {cols.map((c) => (
              <th key={c} className="px-3 py-2">
                {COL_LABELS[c] ?? c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(data.lines as ReadonlyArray<Record<string, unknown>>).map((line) => (
            <tr key={String(line.seq)} className="border-b last:border-0">
              <td className="px-3 py-1.5">{String(line.seq)}</td>
              {cols.map((c) => (
                <td key={c} className="px-2 py-1">
                  <Input
                    className={cn("h-8", c === "declare_elements" && "min-w-[240px]")}
                    value={String(line[c] ?? "")}
                    onChange={(e) => {
                      const raw = e.target.value;
                      const numCols = ["qty", "unit_price", "amount", "box_count", "gross_kg", "net_kg"];
                      onPatchLine(Number(line.seq), {
                        [c]: numCols.includes(c) ? (raw === "" ? 0 : Number(raw)) : raw,
                      });
                    }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
