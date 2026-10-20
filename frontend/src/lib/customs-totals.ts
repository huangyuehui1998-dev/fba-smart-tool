import type { CustomsPackageData } from "@/lib/api/customs";

export function recomputeCustomsTotals(data: CustomsPackageData): CustomsPackageData {
  const lines = data.lines ?? [];
  const total_qty = lines.reduce((sum, ln) => sum + (Number(ln.qty) || 0), 0);
  const total_amount = lines.reduce((sum, ln) => sum + (Number(ln.amount) || 0), 0);
  const total_gross_kg = lines.reduce((sum, ln) => sum + (Number(ln.gross_kg) || 0), 0);
  const total_net_kg = lines.reduce((sum, ln) => sum + (Number(ln.net_kg) || 0), 0);
  const total_pieces = lines.reduce((sum, ln) => sum + (Number(ln.box_count) || 0), 0);
  return {
    ...data,
    lines,
    total_qty,
    total_amount: Math.round(total_amount * 100) / 100,
    total_gross_kg: Math.round(total_gross_kg * 1000) / 1000,
    total_net_kg: Math.round(total_net_kg * 1000) / 1000,
    total_pieces,
  };
}

export function patchCustomsLine(
  data: CustomsPackageData,
  seq: number,
  patch: Record<string, unknown>,
): CustomsPackageData {
  const lines = data.lines.map((ln) => {
    if (ln.seq !== seq) return ln;
    const next = { ...ln, ...patch } as typeof ln;
    const qty = Number(next.qty) || 0;
    const unitPrice = Number(next.unit_price) || 0;
    if ("qty" in patch || "unit_price" in patch) {
      next.amount = Math.round(qty * unitPrice * 100) / 100;
    }
    if ("qty" in patch && "unit_price" in patch && qty > 0 && !patch.unit_price) {
      const amount = Number(next.amount) || 0;
      next.unit_price = Math.round((amount / qty) * 100) / 100;
    }
    return next;
  });
  return recomputeCustomsTotals({ ...data, lines });
}

export function averageUnitPrice(totalAmount: number, totalQty: number): number {
  if (!totalQty) return 0;
  return Math.round((totalAmount / totalQty) * 100) / 100;
}
