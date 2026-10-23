export interface CartonWizardDraft {
  sku: string;
  unit: "cm" | "in";
  length: string;
  width: string;
  height: string;
  qty: string;
  gross: string;
  tare: string;
  unitWeight: string;
}

export const EMPTY_CARTON_DRAFT: CartonWizardDraft = {
  sku: "",
  unit: "cm",
  length: "",
  width: "",
  height: "",
  qty: "",
  gross: "",
  tare: "",
  unitWeight: "",
};

const IN_TO_CM = 2.54;
const OVERSIZE_CM = 63.5;
const OVERWEIGHT_KG = 23;
const API_GROSS_MAX_KG = 70;

export function toCm(value: string, unit: "cm" | "in"): number | null {
  const parsed = Number(String(value).trim());
  if (!Number.isFinite(parsed)) return null;
  return unit === "in" ? parsed * IN_TO_CM : parsed;
}

export function cartonWizardStepBlockers(draft: CartonWizardDraft, step: number): string[] {
  if (step <= 0) {
    return draft.sku.trim() ? [] : ["请填写 SKU"];
  }
  if (step === 1) {
    const blockers: string[] = [];
    const length = toCm(draft.length, draft.unit);
    const width = toCm(draft.width, draft.unit);
    const height = toCm(draft.height, draft.unit);
    if (length == null || length <= 0) blockers.push("请填写长度");
    if (width == null || width <= 0) blockers.push("请填写宽度");
    if (height == null || height <= 0) blockers.push("请填写高度");
    return blockers;
  }
  if (step === 2) {
    const blockers: string[] = [];
    const qty = Number(draft.qty);
    if (!Number.isInteger(qty) || qty <= 0) blockers.push("单箱数量必须是大于 0 的整数");
    const gross = Number(draft.gross);
    if (!Number.isFinite(gross) || gross <= 0) blockers.push("请填写单箱毛重");
    return blockers;
  }
  return cartonWizardReview(draft).blockers;
}

export function cartonWizardReview(draft: CartonWizardDraft): { blockers: string[]; warnings: string[] } {
  const blockers: string[] = [];
  const warnings: string[] = [];
  if (!draft.sku.trim()) blockers.push("请填写 SKU");
  const length = toCm(draft.length, draft.unit);
  const width = toCm(draft.width, draft.unit);
  const height = toCm(draft.height, draft.unit);
  if (length == null || length <= 0) blockers.push("请填写长度");
  if (width == null || width <= 0) blockers.push("请填写宽度");
  if (height == null || height <= 0) blockers.push("请填写高度");
  const qty = Number(draft.qty);
  if (!Number.isInteger(qty) || qty <= 0) blockers.push("单箱数量必须是大于 0 的整数");
  const gross = Number(draft.gross);
  if (!Number.isFinite(gross) || gross <= 0) blockers.push("请填写单箱毛重");
  if (blockers.length) return { blockers, warnings };

  const longest = Math.max(length ?? 0, width ?? 0, height ?? 0);
  if (longest > OVERSIZE_CM) warnings.push(`最长边 ${longest.toFixed(1)} cm，超过 63.5 cm，请核对是否超尺寸`);
  if (gross > API_GROSS_MAX_KG) {
    blockers.push(`单箱毛重 ${gross} kg，超过系统上限 ${API_GROSS_MAX_KG} kg，无法保存`);
  } else if (gross > OVERWEIGHT_KG) {
    warnings.push(`单箱毛重 ${gross} kg，超过 23 kg，请核对是否超重`);
  }
  const tare = Number(draft.tare);
  const unitWeight = Number(draft.unitWeight);
  if (Number.isFinite(tare) && tare > 0 && Number.isFinite(unitWeight) && unitWeight > 0 && qty > 0) {
    const expected = unitWeight * qty + tare;
    if (expected > 0 && Math.abs(gross - expected) / expected > 0.1) {
      warnings.push("毛重和单件重×数量+皮重相差超过 10%");
    }
  }
  const volumeWeight = ((length ?? 0) * (width ?? 0) * (height ?? 0)) / 6000;
  if (volumeWeight > 0) warnings.push(`体积重约 ${volumeWeight.toFixed(2)} kg（÷6000）`);
  return { blockers, warnings };
}

export function cartonWizardPayload(draft: CartonWizardDraft): Record<string, unknown> {
  return {
    sku: draft.sku.trim(),
    length_cm: Number(toCm(draft.length, draft.unit)?.toFixed(2)),
    width_cm: Number(toCm(draft.width, draft.unit)?.toFixed(2)),
    height_cm: Number(toCm(draft.height, draft.unit)?.toFixed(2)),
    qty_per_carton: Number(draft.qty),
    gross_kg: Number(draft.gross),
    tare_kg: draft.tare.trim() ? Number(draft.tare) : undefined,
    unit_kg: draft.unitWeight.trim() ? Number(draft.unitWeight) : undefined,
    source: "manual",
  };
}
