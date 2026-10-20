import type { Row } from "@/lib/step1-rows";

export interface CartonSpecOption {
  id: number;
  spec_name: string;
  qty_per_carton: number;
  length_cm: number;
  width_cm: number;
  height_cm: number;
  gross_kg: number;
  is_default: boolean;
}

export function applyCartonSpec(row: Row, spec: CartonSpecOption): Row {
  return {
    ...row,
    perBox: String(spec.qty_per_carton ?? ""),
    l: String(spec.length_cm ?? ""),
    w: String(spec.width_cm ?? ""),
    h: String(spec.height_cm ?? ""),
    grossKg: spec.gross_kg == null ? row.grossKg : String(spec.gross_kg),
  };
}
