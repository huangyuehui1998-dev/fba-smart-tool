import { FolderOpen } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  fetchUserFormulas,
  fetchUserSettings,
  resetUserConfig,
  saveUserFormulas,
  saveUserSettings,
  type UserFormulas,
  type UserParameters,
  type UserSettings,
} from "@/lib/api/config";
import { formatApiError } from "@/lib/format-api-error";
import { ConfirmDialog } from "@/components/feedback/confirm-dialog";

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs font-medium text-foreground">{label}</Label>
      {children}
      {hint && <p className="text-[10px] leading-tight text-muted-foreground">{hint}</p>}
    </div>
  );
}

const DEFAULT_PARAMS: UserParameters = {
  weight_limit_kg: 22.5,
  max_mixed_items_per_box: 40,
  throw_ratio: 6000,
  volume_divisor: 6000,
  kg_to_lb_factor: 2.20462,
  inch_to_cm_factor: 2.54,
  internal_gross_lb_factor: 2.2,
  sta_box_prefix: "P1 - B",
  factory_box_label_prefix: "纸箱",
  factory_data_start_row: 4,
  forwarder_data_start_row: 3,
  input_template_blank_rows: 10,
  price_max: 100000,
};

type ParamKey = keyof typeof DEFAULT_PARAMS;

const PARAM_FIELDS: { key: ParamKey; label: string; step?: string; span?: 2 }[] = [
  { key: "weight_limit_kg", label: "单箱重量上限 (kg)", step: "0.1" },
  { key: "max_mixed_items_per_box", label: "混装单箱最大件数" },
  { key: "throw_ratio", label: "抛重系数" },
  { key: "volume_divisor", label: "体积重除数" },
  { key: "kg_to_lb_factor", label: "kg → lb 系数", step: "0.00001" },
  { key: "inch_to_cm_factor", label: "in → cm 系数", step: "0.01" },
  { key: "internal_gross_lb_factor", label: "内部表 kg → lb", step: "0.01" },
  { key: "sta_box_prefix", label: "亚马逊箱唛前缀", span: 2 },
  { key: "factory_box_label_prefix", label: "工厂纸箱编号前缀", span: 2 },
  { key: "factory_data_start_row", label: "工厂表数据起始行" },
  { key: "forwarder_data_start_row", label: "货代表数据起始行" },
  { key: "input_template_blank_rows", label: "录入样表空白行数" },
  { key: "price_max", label: "价格上限（美元，超过视为无效价格）" },
];

function mergeParams(raw: UserParameters | undefined): UserParameters {
  return { ...DEFAULT_PARAMS, ...(raw ?? {}) };
}

function parseNumberInput(value: string, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function ParamsSection({ onSaved }: { onSaved?: () => void }) {
  const [parameters, setParameters] = useState<UserParameters>(DEFAULT_PARAMS);
  const [settingsMeta, setSettingsMeta] = useState<Omit<UserSettings, "parameters">>({
    factory_warehouse_columns: {},
    forwarder_column_map: {},
  });
  const [formulasText, setFormulasText] = useState("{}");
  const [whColumnsText, setWhColumnsText] = useState("{}");
  const [loading, setLoading] = useState(true);
  const [confirmReset, setConfirmReset] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [settings, formulas] = await Promise.all([fetchUserSettings(), fetchUserFormulas()]);
      setParameters(mergeParams(settings.parameters));
      setSettingsMeta({
        factory_warehouse_columns: settings.factory_warehouse_columns ?? {},
        forwarder_column_map: settings.forwarder_column_map ?? {},
      });
      setFormulasText(JSON.stringify(formulas, null, 2));
      setWhColumnsText(JSON.stringify(settings.factory_warehouse_columns ?? {}, null, 2));
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const updateParam = (key: ParamKey, value: string | number) => {
    setParameters((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      let formulas: UserFormulas;
      let factoryWh: Record<string, string>;
      try {
        formulas = JSON.parse(formulasText) as UserFormulas;
      } catch {
        throw new Error("Excel 公式模板 JSON 格式无效");
      }
      try {
        factoryWh = JSON.parse(whColumnsText) as Record<string, string>;
      } catch {
        throw new Error("仓库列映射 JSON 格式无效");
      }

      const settings: UserSettings = {
        parameters,
        factory_warehouse_columns: factoryWh,
        forwarder_column_map: settingsMeta.forwarder_column_map ?? {},
      };

      await saveUserSettings(settings);
      await saveUserFormulas(formulas);
      setSuccess("已保存到 app_data/config/，下次启动自动生效。");
      onSaved?.();
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setConfirmReset(true);
  };

  const applyReset = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await resetUserConfig();
      setParameters(mergeParams(res.settings.parameters));
      setSettingsMeta({
        factory_warehouse_columns: res.settings.factory_warehouse_columns ?? {},
        forwarder_column_map: res.settings.forwarder_column_map ?? {},
      });
      setFormulasText(JSON.stringify(res.formulas, null, 2));
      setWhColumnsText(JSON.stringify(res.settings.factory_warehouse_columns ?? {}, null, 2));
      setSuccess("已恢复默认配置。");
      onSaved?.();
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-xs text-muted-foreground">加载配置中…</p>;
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-[11px] text-destructive">{error}</p>}
      {success && <p className="text-[11px] text-emerald-600">{success}</p>}

      <Accordion type="multiple" defaultValue={[]} className="space-y-2">
        <AccordionItem value="biz" className="rounded-md border border-border px-3">
          <AccordionTrigger className="text-xs font-semibold hover:no-underline">
            业务参数
          </AccordionTrigger>
          <AccordionContent className="pb-3">
            <div className="grid grid-cols-2 gap-3">
              {PARAM_FIELDS.map(({ key, label, step, span }) => {
                const value = parameters[key] ?? DEFAULT_PARAMS[key];
                const isText = key === "sta_box_prefix" || key === "factory_box_label_prefix";
                return (
                  <div key={key} className={span === 2 ? "col-span-2" : undefined}>
                    <Field label={label}>
                      {isText ? (
                        <Input
                          value={String(value ?? "")}
                          onChange={(e) => updateParam(key, e.target.value)}
                        />
                      ) : (
                        <Input
                          type="number"
                          step={step}
                          value={String(value ?? "")}
                          onChange={(e) =>
                            updateParam(
                              key,
                              parseNumberInput(e.target.value, Number(DEFAULT_PARAMS[key] ?? 0)),
                            )
                          }
                        />
                      )}
                    </Field>
                  </div>
                );
              })}
            </div>
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="formula" className="rounded-md border border-border px-3">
          <AccordionTrigger className="text-xs font-semibold hover:no-underline">
            Excel 公式模板
          </AccordionTrigger>
          <AccordionContent className="pb-3">
            <Textarea
              value={formulasText}
              onChange={(e) => setFormulasText(e.target.value)}
              className="min-h-[180px] font-mono text-[11px]"
            />
          </AccordionContent>
        </AccordionItem>

        <AccordionItem value="mapping" className="rounded-md border border-border px-3">
          <AccordionTrigger className="text-xs font-semibold hover:no-underline">
            仓库列映射
          </AccordionTrigger>
          <AccordionContent className="pb-3">
            <p className="mb-2 text-[10px] text-muted-foreground">
              留空 {"{}"} 则自动从工厂表识别；也可手动指定列号 → 仓库代码。
            </p>
            <Textarea
              value={whColumnsText}
              onChange={(e) => setWhColumnsText(e.target.value)}
              className="min-h-[120px] font-mono text-[11px]"
            />
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      <div className="flex flex-wrap gap-2 pt-2">
        <Button size="sm" disabled={saving} onClick={() => void handleSave()}>
          {saving ? "保存中…" : "保存配置"}
        </Button>
        <Button size="sm" variant="outline" disabled={saving} onClick={() => void handleReset()}>
          恢复默认
        </Button>
        <Button
          size="sm"
          variant="ghost"
          className="gap-1"
          type="button"
          onClick={() =>
            window.alert(
              "app_data/config/user_settings.json — 业务参数\n" +
                "app_data/config/formulas.json — Excel 公式\n" +
                "app_data/config/sku_mapping.json — SKU 简写映射\n" +
                "app_data/templates/*.xlsx — 表格版式",
            )
          }
        >
          <FolderOpen className="h-3.5 w-3.5" /> config 说明
        </Button>
      </div>
      <ConfirmDialog
        open={confirmReset}
        title="恢复默认参数"
        description="确定恢复为出厂默认参数与公式？"
        confirmLabel="恢复默认"
        onConfirm={() => {
          setConfirmReset(false);
          void applyReset();
        }}
        onCancel={() => setConfirmReset(false)}
      />
    </div>
  );
}
