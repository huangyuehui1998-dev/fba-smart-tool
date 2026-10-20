import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { CustomsPackageData } from "@/lib/api/customs";
import { updateCustomsRuleProfile } from "@/lib/api/master-data";
import {
  DECLARED_VALUE_BASES,
  DECLARED_VALUE_CFR_NOTE,
  NET_RATIO_NOTICE,
  NET_WEIGHT_MODE_NOTICE,
  NET_WEIGHT_MODES,
} from "@/lib/customs-notices";

export function Step5DeclaredValue({
  data,
  onPatch,
}: {
  data: CustomsPackageData | null;
  onPatch: (patch: Partial<CustomsPackageData>) => void;
}) {
  const [profileError, setProfileError] = useState<string | null>(null);
  const [draftBasis, setDraftBasis] = useState("retail");
  const [draftMode, setDraftMode] = useState("tare_from_carton");
  const basis = data?.declared_value_basis || draftBasis;
  const mode = data?.net_weight_mode || draftMode;

  async function saveProfile(patch: Record<string, unknown>, local: Partial<CustomsPackageData>) {
    setProfileError(null);
    onPatch(local);
    try {
      await updateCustomsRuleProfile(patch);
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "规则未保存");
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
      <FxField label="汇率 fx_rate" value={data?.fx_rate ?? ""} onChange={(v) => onPatch({ fx_rate: v === "" ? null : Number(v) })} />
      <FxField label="汇率类型" value={data?.fx_rate_type ?? ""} onChange={(v) => onPatch({ fx_rate_type: v })} />
      <FxField label="适用月份" value={data?.fx_applicable_month ?? ""} onChange={(v) => onPatch({ fx_applicable_month: v })} />
      <FxField label="发布日期" value={data?.fx_publish_date ?? ""} onChange={(v) => onPatch({ fx_publish_date: v })} />
      <div className="md:col-span-2">
        <FxField label="汇率出处" value={data?.fx_source_url ?? ""} onChange={(v) => onPatch({ fx_source_url: v })} />
      </div>
      {profileError && <p className="text-xs text-destructive md:col-span-2">{profileError}</p>}
    </div>
  );
}

function FxField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | number;
  onChange: (value: string) => void;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-muted-foreground">{label}</Label>
      <Input value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}
