import { useEffect, useState } from "react";

import { ConfirmDialog } from "@/components/feedback/confirm-dialog";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError } from "@/lib/api/client";
import type { CustomsPackageData } from "@/lib/api/customs";
import { fetchCustomsRuleProfile, updateCustomsRuleProfile } from "@/lib/api/master-data";
import {
  DECLARED_VALUE_BASES,
  DECLARED_VALUE_CFR_NOTE,
  NET_RATIO_NOTICE,
  NET_WEIGHT_MODE_NOTICE,
  NET_WEIGHT_MODES,
} from "@/lib/customs-notices";

const CUSTOMS_MONTHLY_SOURCE =
  "CFETS 人民币汇率中间价，上月第三个星期三；非银行间外汇市场交易日顺延到下一交易日";

export function Step5DeclaredValue({
  data,
  onPatch,
  declarationDate,
  onDeclarationDate,
  onProfileSaved,
}: {
  data: CustomsPackageData | null;
  onPatch: (patch: Partial<CustomsPackageData>) => void;
  declarationDate: string;
  onDeclarationDate: (value: string) => void;
  onProfileSaved?: () => void;
}) {
  const [profileError, setProfileError] = useState<string | null>(null);
  const [draftBasis, setDraftBasis] = useState("retail");
  const [draftMode, setDraftMode] = useState("tare_from_carton");
  const [taxBasis, setTaxBasis] = useState("month_first");
  const [pendingTax, setPendingTax] = useState<string | null>(null);
  const basis = data?.declared_value_basis || draftBasis;
  const mode = data?.net_weight_mode || draftMode;

  useEffect(() => {
    void fetchCustomsRuleProfile()
      .then((profile) => {
        if (typeof profile.tax_fx_basis === "string" && profile.tax_fx_basis) {
          setTaxBasis(profile.tax_fx_basis);
        }
      })
      .catch(() => undefined);
  }, []);

  async function saveProfile(patch: Record<string, unknown>, local: Partial<CustomsPackageData>) {
    setProfileError(null);
    onPatch(local);
    try {
      await updateCustomsRuleProfile(patch);
      if ("declared_value_basis" in patch) onProfileSaved?.();
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "规则未保存");
    }
  }

  async function saveTaxBasis(next: string, confirm = false) {
    setProfileError(null);
    try {
      const saved = await updateCustomsRuleProfile({ tax_fx_basis: next, confirm });
      setTaxBasis(String(saved.tax_fx_basis || next));
      setPendingTax(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "规则未保存";
      if (message.includes("12 个月内")) {
        setPendingTax(next);
        return;
      }
      setProfileError(message);
    }
  }

  return (
    <div className="grid gap-3 rounded-lg border border-border bg-card p-4 text-sm md:grid-cols-2">
      <div className="space-y-2 md:col-span-2">
        <Label htmlFor="declared-value-basis">申报价口径</Label>
        <select
          id="declared-value-basis"
          className="w-full rounded border px-2 py-1"
          value={basis}
          onChange={(e) => {
            setDraftBasis(e.target.value);
            void saveProfile(
              { declared_value_basis: e.target.value },
              { declared_value_basis: e.target.value },
            );
          }}
        >
          {DECLARED_VALUE_BASES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <p className="text-xs text-muted-foreground">{DECLARED_VALUE_CFR_NOTE}</p>
      </div>
      <div className="space-y-2 md:col-span-2">
        <Label htmlFor="net-weight-mode">净重口径</Label>
        <select
          id="net-weight-mode"
          className="w-full rounded border px-2 py-1"
          value={mode}
          onChange={(e) => {
            setDraftMode(e.target.value);
            void saveProfile({ net_weight_mode: e.target.value }, { net_weight_mode: e.target.value });
          }}
        >
          {NET_WEIGHT_MODES.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        {mode === "tare_from_carton" && (
          <Alert>
            <AlertDescription>{NET_WEIGHT_MODE_NOTICE}</AlertDescription>
          </Alert>
        )}
        {mode === "ratio" && <p className="text-xs text-muted-foreground">{NET_RATIO_NOTICE}</p>}
      </div>
      <div className="space-y-2">
        <Label htmlFor="declaration-date">报关完成申报之日</Label>
        <Input
          id="declaration-date"
          type="date"
          value={declarationDate}
          onChange={(e) => onDeclarationDate(e.target.value)}
        />
        <p className="text-xs text-muted-foreground">适用月份按这一天确定，不按发货日或导出日。</p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="tax-fx-basis">出口退税折合率</Label>
        <select
          id="tax-fx-basis"
          className="w-full rounded border px-2 py-1"
          value={taxBasis}
          onChange={(e) => void saveTaxBasis(e.target.value)}
        >
          <option value="day">销售额发生当日</option>
          <option value="month_first">当月 1 日</option>
        </select>
      </div>
      <p className="text-xs text-muted-foreground md:col-span-2">{CUSTOMS_MONTHLY_SOURCE}</p>
      <FxField id="fx-rate-input" label="汇率 fx_rate" value={data?.fx_rate ?? ""} onChange={(v) => onPatch({ fx_rate: v === "" ? null : Number(v) })} />
      <FxField label="汇率类型" value={data?.fx_rate_type ?? ""} onChange={(v) => onPatch({ fx_rate_type: v })} />
      <FxField label="适用月份" value={data?.fx_applicable_month ?? ""} onChange={(v) => onPatch({ fx_applicable_month: v })} />
      <FxField label="发布日期" value={data?.fx_publish_date ?? ""} onChange={(v) => onPatch({ fx_publish_date: v })} />
      <div className="md:col-span-2">
        <FxField label="汇率出处" value={data?.fx_source_url ?? ""} onChange={(v) => onPatch({ fx_source_url: v })} />
      </div>
      {profileError && <p className="text-xs text-destructive md:col-span-2">{profileError}</p>}
      <ConfirmDialog
        open={pendingTax != null}
        title="出口退税折合率 12 个月内不得变更"
        description="确定后 12 个月内不能再改。确认后才会写入新的口径。"
        confirmLabel="确认变更"
        onCancel={() => setPendingTax(null)}
        onConfirm={() => {
          if (pendingTax) void saveTaxBasis(pendingTax, true);
        }}
      />
    </div>
  );
}

function FxField({
  id,
  label,
  value,
  onChange,
}: {
  id?: string;
  label: string;
  value: string | number;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-muted-foreground">{label}</Label>
      <Input id={id} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
