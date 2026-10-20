import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import type { LingxingPreviewPayload, LingxingPreviewPriceVariant, LingxingPreviewSku } from "@/lib/api/lingxing";
import { confirmNormalPrice } from "@/lib/api/master-data";
import { cn } from "@/lib/utils";

const GROUP_ORDER = [
  { key: "new", title: "新增 SKU" },
  { key: "needs_review", title: "新品待人工确认（SKU 像乱码 / 缺 FNSKU / 缺 ASIN，默认不写入）" },
  { key: "changed", title: "有变更" },
  { key: "sku_mismatch", title: "同 ASIN 本地已有其他 SKU（默认不写入）" },
  { key: "unchanged", title: "无变化" },
] as const;

function defaultsFromPreview(preview: LingxingPreviewPayload): Record<string, string[]> {
  const next: Record<string, string[]> = {};
  for (const group of Object.values(preview.groups || {})) {
    for (const sku of group || []) {
      const fields = (sku.fields || []).filter((f) => f.default_checked).map((f) => f.field);
      if (fields.length) next[sku.sku] = fields;
    }
  }
  return next;
}

const PRICE_FIELD_ORDER = ["listing_price", "regular_price"] as const;

function fmtPrice(v: number | null | undefined, currency?: string): string {
  if (v === null || v === undefined) return "（空）";
  return `${currency ? `${currency} ` : ""}${v.toFixed(2)}`;
}

function originText(origin: string, at?: string): string {
  if (origin === "remote") return "（本次领星）";
  if (origin === "local") return at ? `（本地旧值 · ${at} 采集）` : "（本地旧值）";
  return "";
}

/** S9-step2-fix U1：按当前勾选的价格字段取对应的申报价结果（取消勾选售价/常规价时联动）。 */
export function pickPriceVariant(row: LingxingPreviewSku, selected: Set<string>): LingxingPreviewPriceVariant | null {
  const info = row.price_info;
  if (!info) return null;
  const offered = new Set(info.price_fields || []);
  const key = PRICE_FIELD_ORDER.filter((f) => offered.has(f) && selected.has(f)).join("+");
  return info.variants?.[key] ?? info;
}

/** 一段价格说明：段内不换行（UI c），整行按段换行。 */
function Seg({ children, className }: { children: ReactNode; className?: string }) {
  return <span className={cn("whitespace-nowrap", className)}>{children}</span>;
}

function PriceLine({ info }: { info: LingxingPreviewPriceVariant }) {
  const cur = info.currency;
  const above = info.promo && info.declared_above_listing;
  return (
    <div className="mt-0.5 text-muted-foreground" data-testid="lingxing-preview-price">
      <div className="flex flex-wrap gap-x-2 gap-y-0.5">
        {/* S9-step4：价格和来源分成两段，窄屏（420px）时来源可单独折到下一行，不横向溢出 */}
        <Seg>售价 {fmtPrice(info.listing_price, cur)}</Seg>
        {originText(info.listing_price_origin) && <Seg>{originText(info.listing_price_origin)}</Seg>}
        <Seg>· 领星常规价 {fmtPrice(info.regular_price, cur)}</Seg>
        {originText(info.regular_price_origin, info.regular_price_at) && (
          <Seg>{originText(info.regular_price_origin, info.regular_price_at)}</Seg>
        )}
        {info.regular_price !== null && info.regular_price_expired && (
          <Seg data-testid="lingxing-preview-regular-expired">（采集超过 90 天，不作为正常价）</Seg>
        )}
        {info.regular_price !== null && !info.regular_price_expired && !info.regular_price_informative && (
          <Seg>（不高于售价，不作为正常价）</Seg>
        )}
        {info.regular_gap_text && <span data-testid="lingxing-preview-gap">· {info.regular_gap_text}</span>}
        {info.promo && (
          <span className="flex flex-wrap gap-x-1 font-medium text-amber-600">
            <Seg>· 促销中：</Seg>
            <Seg>比正常价 {fmtPrice(info.normal_price, cur)}</Seg>
            {info.normal_basis_label && <Seg>（{info.normal_basis_label}）</Seg>}
            <Seg>{info.promo_drop_text || "降幅未知"}</Seg>
          </span>
        )}
      </div>
      <div
        className={cn(
          "mt-0.5 flex flex-wrap gap-x-2 font-medium text-foreground",
          above && "rounded bg-amber-100 px-1 py-0.5 text-amber-900 dark:bg-amber-500/20 dark:text-amber-100",
        )}
        data-testid="lingxing-preview-declared"
      >
        <Seg>
          确认写入后申报将用：
          {info.declared_price === null ? "无有效申报价" : fmtPrice(info.declared_price, cur)}
        </Seg>
        {info.declared_source_label && <Seg>· 来源：{info.declared_source_label}</Seg>}
        {above && <Seg className="font-semibold">· 高于售价：促销期按正常价申报</Seg>}
      </div>
      {(info.warnings || []).map((w) => (
        <span key={w} className="block text-amber-600 [overflow-wrap:anywhere]">
          ⚠ {w}
        </span>
      ))}
    </div>
  );
}

/** S9-step4（D-15）：S9-B 提示 + 人工确认正常价（默认是将要申报的价，可改）。只提示，不改申报价规则。 */
function HistoryHint({
  sku,
  info,
  isNew,
  onConfirmed,
}: {
  sku: string;
  info: LingxingPreviewPriceVariant;
  isNew: boolean;
  onConfirmed?: () => void;
}) {
  const [value, setValue] = useState(info.declared_price !== null ? info.declared_price.toFixed(2) : "");
  const [busy, setBusy] = useState(false);
  if (!info.history_hint) return null;
  const submit = async () => {
    setBusy(true);
    // S9-step4-fix3：确认成功时清掉之前的错误提示；S9-final N6：成功提示用独立的 id，不会被 dismiss 吞掉
    const toastId = `confirm-normal-price-${sku}`;
    const okToastId = `confirm-normal-price-ok-${sku}`;
    try {
      const res = await confirmNormalPrice(sku, value);
      toast.dismiss(toastId);
      toast.success(`已确认 ${res.sku} 的正常价：${res.price.toFixed(2)}`, { id: okToastId });
      onConfirmed?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err), { id: toastId });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div
      className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 rounded bg-amber-50 px-1 py-0.5 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
      data-testid="lingxing-preview-history-hint"
    >
      <span className="font-medium">⚠ {info.history_hint}</span>
      {isNew ? (
        <span className="text-muted-foreground">（写入产品库后可在这里确认正常价）</span>
      ) : (
        <span className="flex flex-wrap items-center gap-1">
          <span>正常价</span>
          <Input
            className="h-6 w-24 px-1 text-xs"
            inputMode="decimal"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-label="人工确认的正常价"
          />
          <Button type="button" size="sm" variant="outline" className="h-6 px-2 text-xs" disabled={busy} onClick={() => void submit()}>
            {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
            确认为正常价
          </Button>
        </span>
      )}
    </div>
  );
}

function allSkus(preview: LingxingPreviewPayload): LingxingPreviewSku[] {
  return GROUP_ORDER.flatMap((g) => preview.groups?.[g.key] || []);
}

export function LingxingPreviewPanel({
  preview,
  confirming,
  onConfirm,
  onPriceConfirmed,
}: {
  preview: LingxingPreviewPayload;
  confirming: boolean;
  onConfirm: (items: { sku: string; fields: string[] }[]) => void;
  /** S9-step4：人工确认正常价后刷新预览 */
  onPriceConfirmed?: () => void;
}) {
  const [checked, setChecked] = useState<Record<string, string[]>>(() => defaultsFromPreview(preview));
  const [openSkus, setOpenSkus] = useState<Set<string>>(() => new Set()); // UI b：可同时展开多个 SKU
  const toggleOpen = (sku: string) =>
    setOpenSkus((prev) => {
      const next = new Set(prev);
      if (next.has(sku)) next.delete(sku);
      else next.add(sku);
      return next;
    });

  useEffect(() => {
    setChecked(defaultsFromPreview(preview));
    setOpenSkus(new Set());
  }, [preview.run_id, preview.status]);

  const selectedCount = useMemo(
    () => Object.values(checked).reduce((n, fields) => n + fields.length, 0),
    [checked],
  );

  const toggleField = (sku: string, field: string, on: boolean) => {
    setChecked((prev) => {
      const curr = new Set(prev[sku] || []);
      if (on) curr.add(field);
      else curr.delete(field);
      const next = { ...prev };
      if (curr.size) next[sku] = [...curr];
      else delete next[sku];
      return next;
    });
  };

  const applyDefaults = () => setChecked(defaultsFromPreview(preview));
  const clearAll = () => setChecked({});

  if (!preview.pending) {
    return null;
  }

  return (
    <div className="min-w-0 max-w-full space-y-3 rounded-md border border-border bg-muted/20 p-3 [overflow-wrap:anywhere]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">产品主表待确认</p>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" onClick={applyDefaults} disabled={confirming}>
            恢复默认勾选
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={clearAll} disabled={confirming}>
            全不选
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() =>
              onConfirm(
                Object.entries(checked).map(([sku, fields]) => ({ sku, fields })),
              )
            }
            disabled={confirming}
          >
            {confirming ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            确认写入主库（{selectedCount} 个字段）
          </Button>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        库存/补货已更新。ASIN、FNSKU 等身份变更默认勾选。本地已有英文名/品牌默认不覆盖。箱规与报关中文/HS 不会出现在此清单。
      </p>
      <p className="text-xs text-muted-foreground" data-testid="lingxing-preview-terms">
        用词：“领星常规价”指领星的常规价字段；“正常价”指判断促销时参考的价格：领星常规价高于售价时取领星常规价，否则取近 90 天非促销价。售价比正常价低 5% 以上才算促销，按正常价申报；低不到 5% 不算促销，按售价申报。点 SKU 行（▸）展开，勾选要写入的字段。
      </p>
      <div className="space-y-3 text-xs">
        {GROUP_ORDER.map((group) => {
          const rows = preview.groups?.[group.key] || [];
          if (!rows.length) return null;
          // S9-step4-fix3：组里有 S9-B 提示时标题显示提示数；「无变化」组有提示就默认展开
          const hintCount = rows.filter((r) => pickPriceVariant(r, new Set(checked[r.sku] || []))?.history_hint).length;
          const collapsed = group.key === "unchanged" && hintCount === 0;
          return (
            <details key={`${group.key}-${hintCount > 0 ? "hint" : "plain"}`} open={!collapsed} className="rounded border border-border/80 px-2 py-1">
              <summary className="cursor-pointer py-1 font-medium">
                {group.title}（{rows.length}）
                {hintCount > 0 && (
                  <span className="ml-1 font-normal text-amber-700 dark:text-amber-300" data-testid="lingxing-preview-group-hint-count">
                    · ⚠ {hintCount} 个需人工确认正常价
                  </span>
                )}
              </summary>
              <ul className="space-y-2 pb-2">
                {rows.map((row) => {
                  const selected = new Set(checked[row.sku] || []);
                  const expanded = openSkus.has(row.sku);
                  return (
                    <li key={row.sku} className="min-w-0 rounded bg-background/80 px-2 py-1">
                      <button
                        type="button"
                        className="flex w-full flex-wrap items-center justify-between gap-x-2 gap-y-0.5 text-left"
                        onClick={() => toggleOpen(row.sku)}
                        aria-expanded={expanded}
                        title={expanded ? "收起字段" : "点击展开，勾选要写入的字段"}
                      >
                        <span className="flex min-w-0 items-center gap-1 font-medium [overflow-wrap:anywhere]">
                          {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                          {row.sku}
                        </span>
                        <span className="min-w-0 text-muted-foreground">
                          {selected.size}/{row.fields.length} 字段{expanded ? "（点击收起）" : "（点击展开勾选）"}
                          {row.mismatch_skus?.length ? ` · 本地 ${row.mismatch_skus.join("、")}` : ""}
                          {row.review_reasons?.length ? ` · ${row.review_reasons.join("、")}` : ""}
                        </span>
                      </button>
                      {(() => {
                        const info = pickPriceVariant(row, selected);
                        return info ? (
                          <>
                            <PriceLine info={info} />
                            <HistoryHint
                              key={`${row.sku}-${info.declared_price ?? ""}`}
                              sku={row.sku}
                              info={info}
                              isNew={row.is_new}
                              onConfirmed={onPriceConfirmed}
                            />
                          </>
                        ) : null;
                      })()}
                      {expanded && (
                        <div className="mt-2 space-y-1 border-t border-border/60 pt-2">
                          {row.fields.length === 0 && <p className="text-muted-foreground">无可写入字段</p>}
                          {row.fields.map((f) => (
                            <label
                              key={f.field}
                              className={cn(
                                "flex items-start gap-2 rounded px-1 py-1",
                                f.sensitive && "bg-amber-500/5",
                              )}
                            >
                              <Checkbox
                                checked={selected.has(f.field)}
                                onCheckedChange={(v) => toggleField(row.sku, f.field, v === true)}
                                disabled={confirming}
                              />
                              <span>
                                <span className="font-medium">{f.label}</span>
                                {f.sensitive ? "（报关敏感，本地已有则默认不写）" : ""}
                                <span className="mt-0.5 block text-muted-foreground">
                                  本地：{f.local_value || "（空）"} → 领星：{f.remote_value || "（空）"}
                                </span>
                              </span>
                            </label>
                          ))}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            </details>
          );
        })}
        {allSkus(preview).length === 0 && <p className="text-muted-foreground">本次没有可预览的 Listing。</p>}
      </div>
    </div>
  );
}
