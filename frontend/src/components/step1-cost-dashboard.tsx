import { useState } from "react";
import { cn } from "@/lib/utils";
import type { CostDashboard, PlacementLineItem, PlacementOptionKey } from "@/lib/api/step1";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, ChevronDown, ChevronUp } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { TableScrollArea } from "@/components/table-scroll-area";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function fmtUsdRange(min: number | null | undefined, max: number | null | undefined): string {
  if (min == null || max == null) return "—";
  if (min === max) return `$${min.toFixed(2)}`;
  return `$${min.toFixed(2)} - $${max.toFixed(2)}`;
}

function feeCell(fee: { min_usd: number; max_usd: number } | null | undefined): string {
  if (!fee) return "—";
  return fmtUsdRange(fee.min_usd, fee.max_usd);
}

export function Step1CostDashboard({
  data,
  loading,
}: {
  data: CostDashboard | null;
  loading: boolean;
}) {
  const placement = data?.placement;
  const locked = data?.actual_placement_fee;
  const [expanded, setExpanded] = useState<PlacementOptionKey | null>(null);

  const splitEnabled = placement?.split_2_3.enabled ?? false;
  const splitDisabledReason =
    placement?.split_2_3.disabled_reason ?? "标准尺寸商品不支持部分拆分入库";

  const toggleExpand = (key: PlacementOptionKey) => {
    if (key === "split_2_3" && !splitEnabled) return;
    setExpanded((prev) => (prev === key ? null : key));
  };

  return (
    <TooltipProvider delayDuration={200}>
      <Card className="border-amber-200/60 bg-gradient-to-br from-amber-50/40 to-card shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            💰 成本精算控制台
            <span className="text-xs font-normal text-muted-foreground">
              配置费按 Fee Preview 单品尺寸；CBM/排箱/货代按 Step1 外箱录入
            </span>
            {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {locked && (
            <Alert className="border-emerald-300 bg-emerald-50/80">
              <AlertTitle className="text-sm font-semibold text-emerald-900">
                实际费用已锁定（Step 4 回传）
              </AlertTitle>
              <AlertDescription className="space-y-2 text-xs text-emerald-800">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-2xl font-bold tabular-nums text-emerald-900">
                    ${locked.locked_usd.toFixed(2)}
                  </span>
                  <Badge variant="outline" className="border-emerald-400 text-emerald-900">
                    {locked.scenario_label}
                  </Badge>
                  <Badge variant="secondary">
                    {locked.actual_location_count} 仓 · {locked.warehouse_regions.join(" / ")}
                  </Badge>
                </div>
                <p>
                  发货前预估区间 ${locked.applicable_range_min_usd.toFixed(2)} – $
                  {locked.applicable_range_max_usd.toFixed(2)} → 按实际上仓方案锁定为定数（区间上限）。
                </p>
                {locked.applicable_range_mid_usd !== undefined && (
                  <p>
                    定价/毛利测算建议用预期值{" "}
                    <span className="font-semibold tabular-nums">
                      ${locked.applicable_range_mid_usd.toFixed(2)}
                    </span>
                    ；上方锁定值为财务保守预算，直接拿它算毛利会低估利润。
                  </p>
                )}
                <p className="font-mono text-[11px]">
                  目的仓：{locked.actual_warehouses.join(", ")}
                </p>
              </AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
            <PlacementOptionCard
              emoji="🔴"
              title="单点入仓 (1个仓)"
              subtitle="1 Location"
              value={
                placement
                  ? fmtUsdRange(placement.one_location.min_usd, placement.one_location.max_usd)
                  : "—"
              }
              loading={loading}
              active={expanded === "one_location"}
              onClick={() => toggleExpand("one_location")}
            />

            {!splitEnabled ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="h-full">
                    <PlacementOptionCard
                      emoji="🟡"
                      title="部分拆分 (2-3仓)"
                      subtitle="2-3 Locations"
                      value="—"
                      loading={loading}
                      disabled
                      hint="标准尺寸商品不支持部分拆分入库"
                    />
                  </div>
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs">
                  {splitDisabledReason}
                </TooltipContent>
              </Tooltip>
            ) : (
              <PlacementOptionCard
                emoji="🟡"
                title="部分拆分 (2-3仓)"
                subtitle="2-3 Locations"
                value={fmtUsdRange(placement?.split_2_3.min_usd, placement?.split_2_3.max_usd)}
                loading={loading}
                active={expanded === "split_2_3"}
                onClick={() => toggleExpand("split_2_3")}
              />
            )}

            <PlacementOptionCard
              emoji="🟢"
              title="亚马逊优化 (5仓+)"
              subtitle="5+ Locations · 免费"
              value="$0.00"
              loading={loading}
              highlight
            />
          </div>

          {placement && placement.total_units > 0 && (
            <p className="text-[11px] text-muted-foreground">
              共 {placement.total_units} 件 · 可计费 {placement.eligible_units} 件
              {placement.ineligible_units > 0 && (
                <span className="text-amber-700">
                  {" "}
                  · {placement.ineligible_units} 件不在当前费率表覆盖范围
                </span>
              )}
            </p>
          )}

          {expanded && placement?.line_items?.length ? (
            <PlacementDetailTable
              option={expanded}
              items={placement.line_items}
              onClose={() => setExpanded(null)}
            />
          ) : null}
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}

function PlacementOptionCard({
  emoji,
  title,
  subtitle,
  value,
  loading,
  disabled,
  hint,
  highlight,
  active,
  onClick,
}: {
  emoji: string;
  title: string;
  subtitle: string;
  value: string;
  loading: boolean;
  disabled?: boolean;
  hint?: string;
  highlight?: boolean;
  active?: boolean;
  onClick?: () => void;
}) {
  const clickable = Boolean(onClick) && !disabled;

  return (
    <button
      type="button"
      disabled={!clickable}
      onClick={onClick}
      className={cn(
        "rounded-md border px-3 py-2.5 text-left transition-colors",
        disabled && "cursor-not-allowed opacity-45",
        highlight && "border-emerald-200 bg-emerald-50/60",
        !highlight && !disabled && "border-border bg-muted/20 hover:bg-muted/40",
        active && "ring-2 ring-primary/30",
        clickable && "cursor-pointer",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-medium">
            {emoji} {title}
          </div>
          <div className="text-[10px] text-muted-foreground">{subtitle}</div>
        </div>
        {clickable && (active ? <ChevronUp className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />)}
      </div>
      <div className="mt-1.5 text-base font-semibold tabular-nums">{loading ? "…" : value}</div>
      {hint && <div className="mt-0.5 text-[10px] text-muted-foreground">{hint}</div>}
    </button>
  );
}

function PlacementDetailTable({
  option,
  items,
  onClose,
}: {
  option: PlacementOptionKey;
  items: PlacementLineItem[];
  onClose: () => void;
}) {
  const title = option === "one_location" ? "单点入仓 · SKU 明细" : "部分拆分 · SKU 明细";

  return (
    <div className="rounded-lg border border-border/80 bg-card/90">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-xs font-semibold">{title}</span>
        <button type="button" className="text-[10px] text-muted-foreground hover:text-foreground" onClick={onClose}>
          收起
        </button>
      </div>
      <TableScrollArea variant="plain">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40">
              <TableHead className="text-xs">SKU</TableHead>
              <TableHead className="text-xs">件数</TableHead>
              <TableHead className="text-xs">计费重量 (lb)</TableHead>
              <TableHead className="text-xs">尺寸分段</TableHead>
              <TableHead className="text-xs">单件费率 (USD)</TableHead>
              <TableHead className="text-xs">小计 (USD)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((row) => {
              const unitFee =
                option === "one_location" ? row.one_location : row.split_2_3;
              const subtotal =
                option === "one_location" ? row.subtotal_one_location : row.subtotal_split_2_3;
              const rowDisabled =
                option === "split_2_3" && (row.split_2_3_disabled || !unitFee);

              return (
                <TableRow key={row.sku} className={cn(rowDisabled && "opacity-50")}>
                  <TableCell className="font-mono text-xs">{row.sku}</TableCell>
                  <TableCell className="text-xs">{row.quantity}</TableCell>
                  <TableCell className="font-mono text-xs">{row.billing_lb.toFixed(3)}</TableCell>
                  <TableCell className="text-xs">{row.size_class_label}</TableCell>
                  <TableCell className="font-mono text-xs">
                    {rowDisabled ? "—" : feeCell(unitFee)}
                  </TableCell>
                  <TableCell className="font-mono text-xs">
                    {rowDisabled ? "—" : feeCell(subtotal)}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableScrollArea>
    </div>
  );
}
