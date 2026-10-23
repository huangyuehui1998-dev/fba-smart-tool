import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  EMPTY_CARTON_DRAFT,
  cartonWizardPayload,
  cartonWizardReview,
  cartonWizardStepBlockers,
  type CartonWizardDraft,
} from "@/lib/carton-wizard";

const STEPS = ["SKU", "外箱尺寸", "数量与重量", "确认"];

export function CartonSpecWizard({
  initialSku = "",
  onSaved,
}: {
  initialSku?: string;
  onSaved?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<CartonWizardDraft>({ ...EMPTY_CARTON_DRAFT, sku: initialSku });
  const [saving, setSaving] = useState(false);
  const review = useMemo(() => cartonWizardReview(draft), [draft]);
  const stepBlockers = useMemo(() => cartonWizardStepBlockers(draft, step), [draft, step]);

  const goNext = () => {
    if (stepBlockers.length) return;
    setStep((value) => value + 1);
  };

  const patch = (partial: Partial<CartonWizardDraft>) => setDraft((prev) => ({ ...prev, ...partial }));

  const save = async () => {
    if (review.blockers.length) {
      toast.error(review.blockers[0]);
      return;
    }
    setSaving(true);
    try {
      const response = await fetch("/api/carton-specs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cartonWizardPayload(draft)),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "保存失败");
      }
      toast.success("箱规已保存");
      setOpen(false);
      setStep(0);
      onSaved?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <Button type="button" size="sm" variant="secondary" data-testid="carton-wizard-open" onClick={() => setOpen(true)}>
        录入箱规
      </Button>
    );
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4" data-testid="carton-wizard">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium" data-testid="carton-step">
          箱规向导 · {STEPS[step]}（{step + 1}/4）
        </p>
        <Button type="button" size="sm" variant="ghost" onClick={() => setOpen(false)}>
          关闭
        </Button>
      </div>
      {step === 0 && (
        <Label className="block space-y-1 text-xs">
          SKU
          <Input data-testid="carton-sku" value={draft.sku} onChange={(event) => patch({ sku: event.target.value })} />
        </Label>
      )}
      {step === 1 && (
        <div className="grid gap-2 sm:grid-cols-4">
          <Label className="space-y-1 text-xs">
            单位
            <select
              className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
              data-testid="carton-unit"
              value={draft.unit}
              onChange={(event) => patch({ unit: event.target.value as "cm" | "in" })}
            >
              <option value="cm">厘米</option>
              <option value="in">英寸</option>
            </select>
          </Label>
          <Label className="space-y-1 text-xs">
            长
            <Input data-testid="carton-length" value={draft.length} onChange={(event) => patch({ length: event.target.value })} />
          </Label>
          <Label className="space-y-1 text-xs">
            宽
            <Input data-testid="carton-width" value={draft.width} onChange={(event) => patch({ width: event.target.value })} />
          </Label>
          <Label className="space-y-1 text-xs">
            高
            <Input data-testid="carton-height" value={draft.height} onChange={(event) => patch({ height: event.target.value })} />
          </Label>
        </div>
      )}
      {step === 2 && (
        <div className="grid gap-2 sm:grid-cols-2">
          <Label className="space-y-1 text-xs">
            单箱数量
            <Input data-testid="carton-qty" value={draft.qty} onChange={(event) => patch({ qty: event.target.value })} />
          </Label>
          <Label className="space-y-1 text-xs">
            单箱毛重 kg
            <Input data-testid="carton-gross" value={draft.gross} onChange={(event) => patch({ gross: event.target.value })} />
          </Label>
          <Label className="space-y-1 text-xs">
            皮重 kg
            <Input value={draft.tare} onChange={(event) => patch({ tare: event.target.value })} />
          </Label>
          <Label className="space-y-1 text-xs">
            单件重 kg
            <Input value={draft.unitWeight} onChange={(event) => patch({ unitWeight: event.target.value })} />
          </Label>
        </div>
      )}
      {step < 3 &&
        stepBlockers.map((item) => (
          <p key={item} className="text-destructive" data-testid="carton-blocker">
            {item}
          </p>
        ))}
      {step === 3 && (
        <div className="space-y-2 text-sm" data-testid="carton-review">
          <p>
            {draft.sku || "未填 SKU"} · {draft.length}×{draft.width}×{draft.height} {draft.unit} · {draft.qty} 件/箱 · 毛重 {draft.gross} kg
          </p>
          {review.blockers.map((item) => (
            <p key={item} className="text-destructive" data-testid="carton-blocker">
              {item}
            </p>
          ))}
          {review.warnings.map((item) => (
            <p key={item} className="text-amber-700" data-testid="carton-warning">
              {item}
            </p>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        {step > 0 && (
          <Button type="button" variant="outline" size="sm" onClick={() => setStep((value) => value - 1)}>
            上一步
          </Button>
        )}
        {step < 3 ? (
          <Button type="button" size="sm" data-testid="carton-next" onClick={goNext}>
            下一步
          </Button>
        ) : (
          <Button type="button" size="sm" data-testid="carton-save" disabled={saving || review.blockers.length > 0} onClick={() => void save()}>
            {saving ? "保存中…" : "保存"}
          </Button>
        )}
      </div>
    </div>
  );
}
