export type ForwarderRow = Record<string, unknown> & {
  _subtotal?: boolean;
  _subtotal_cbm?: number;
};

export type LogisticsProfile = {
  wm_ratio?: string;
  stowage_factor?: number;
  cargo_density?: number;
  revenue_ton?: number;
  total_gross_kg?: number;
  total_volumetric_weight_kg?: number;
  total_cbm?: number;
};

export const FORWARDER_DISPLAY_COLUMNS = [
  "仓库代码",
  "SKU",
  "箱序号",
  "箱数",
  "箱子长(cm)",
  "箱子宽(cm)",
  "箱子高(cm)",
  "单箱体积重(kg)",
  "总体积重(kg)",
  "单箱实重(kg)",
  "总实重(kg)",
  "单箱装量",
  "发货总数",
  "单件实重(kg)",
] as const;

export const FORWARDER_DIM_COLUMNS = ["箱子长(cm)", "箱子宽(cm)", "箱子高(cm)"] as const;

function round(value: number, decimals: number): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

/** 单箱方数 (CBM) = 长 × 宽 × 高 / 1,000,000 */
export function boxCbm(lengthCm: number, widthCm: number, heightCm: number): number {
  if (lengthCm <= 0 || widthCm <= 0 || heightCm <= 0) return 0;
  return round((lengthCm * widthCm * heightCm) / 1_000_000, 3);
}

export function forwarderDetailRowCbm(row: ForwarderRow): number {
  const l = Number(row["箱子长(cm)"]) || 0;
  const w = Number(row["箱子宽(cm)"]) || 0;
  const h = Number(row["箱子高(cm)"]) || 0;
  const boxes = Number(row["箱数"]) || 0;
  if (l <= 0 || w <= 0 || h <= 0 || boxes <= 0) return 0;
  return round(boxCbm(l, w, h) * boxes, 3);
}

export function formatSubtotalCbmLabel(cbm: number): string {
  return `方数: ${cbm.toFixed(3)} CBM`;
}

export function isForwarderSubtotalRow(row: ForwarderRow): boolean {
  if (row._subtotal === true) return true;
  const wh = String(row["仓库代码"] ?? "");
  return wh.endsWith(" 小计");
}

export function forwarderDetailRows(rows: ForwarderRow[]): ForwarderRow[] {
  return rows.filter((r) => !isForwarderSubtotalRow(r));
}

export function isForwarderDimColumn(col: string): boolean {
  return (FORWARDER_DIM_COLUMNS as readonly string[]).includes(col);
}

/** 从工人装箱表列头（如「第二票 FWA4」）解析仓库 -> 票序。 */
export function warehouseRankFromTicketLabels(labels: string[]): Record<string, number> {
  const rank: Record<string, number> = {};
  labels.forEach((label, i) => {
    const trimmed = String(label ?? "").trim();
    if (!trimmed) return;
    const m = trimmed.match(/第[一二三四五六七八九十\d]+票\s+(\S+)/);
    const wh = m?.[1] ?? trimmed.split(/\s+/).pop() ?? trimmed;
    if (wh && !(wh in rank)) rank[wh] = i;
  });
  return rank;
}

/** 按票序对货代表明细分仓排序（与后端 append 小计逻辑一致）。 */
export function sortForwarderByWarehouseTicket(
  rows: ForwarderRow[],
  warehouseTicketRank: Record<string, number>,
): ForwarderRow[] {
  const detail = forwarderDetailRows(rows);
  if (!detail.length) return rows.length ? [] : rows;
  const ranked = [...detail].sort((a, b) => {
    const wa = String(a["仓库代码"] ?? "");
    const wb = String(b["仓库代码"] ?? "");
    const ra = warehouseTicketRank[wa] ?? 9999;
    const rb = warehouseTicketRank[wb] ?? 9999;
    if (ra !== rb) return ra - rb;
    if (wa !== wb) return wa.localeCompare(wb);
    return String(a.SKU ?? "").localeCompare(String(b.SKU ?? ""));
  });
  return ensureForwarderSubtotals(ranked);
}

/** 始终从明细行重建分仓小计（幂等），并写入分仓方数。 */
export function ensureForwarderSubtotals(rows: ForwarderRow[]): ForwarderRow[] {
  const detail = forwarderDetailRows(rows);
  if (!detail.length) return rows.length ? [] : rows;

  const whOrder: string[] = [];
  for (const row of detail) {
    const wh = String(row["仓库代码"] ?? "");
    if (wh && !whOrder.includes(wh)) whOrder.push(wh);
  }

  const out: ForwarderRow[] = [];
  for (const wh of whOrder) {
    const block = detail.filter((r) => String(r["仓库代码"] ?? "") === wh);
    for (const row of block) {
      out.push({ ...row, _subtotal: false });
    }

    const boxSum = block.reduce((s, r) => s + (Number(r["箱数"]) || 0), 0);
    const grossSum = round(
      block.reduce((s, r) => s + (Number(r["总实重(kg)"]) || 0), 0),
      2,
    );
    const volSum = round(
      block.reduce((s, r) => s + (Number(r["总体积重(kg)"]) || 0), 0),
      3,
    );
    const cbmSum = round(block.reduce((s, r) => s + forwarderDetailRowCbm(r), 0), 3);

    out.push({
      仓库代码: `${wh} 小计`,
      SKU: "",
      箱序号: "",
      "单件实重(kg)": "",
      箱数: boxSum,
      "箱子长(cm)": formatSubtotalCbmLabel(cbmSum),
      "箱子宽(cm)": "",
      "箱子高(cm)": "",
      "总实重(kg)": grossSum,
      "总体积重(kg)": volSum,
      _subtotal: true,
      _subtotal_cbm: cbmSum,
    });
  }

  return out;
}

/** 从货代表明细行估算宏观物流指标（API 缺字段时的兜底）。 */
export function computeLogisticsProfileFromForwarder(rows: ForwarderRow[]): LogisticsProfile {
  const detail = forwarderDetailRows(rows);
  if (!detail.length) return {};

  let totalGross = 0;
  let totalVol = 0;
  let totalCbm = 0;

  for (const row of detail) {
    totalGross += Number(row["总实重(kg)"]) || 0;
    totalVol += Number(row["总体积重(kg)"]) || 0;
    totalCbm += forwarderDetailRowCbm(row);
  }

  totalGross = round(totalGross, 3);
  totalVol = round(totalVol, 3);
  totalCbm = round(totalCbm, 3);

  const cargoDensity = totalCbm > 0 ? round(totalGross / totalCbm, 3) : 0;
  const stowageFactor = totalGross > 0 ? round(totalCbm / (totalGross / 1000), 3) : 0;
  const wmRatio = totalGross >= totalVol ? "重货 (Weight)" : "泡货 (Measurement)";

  return {
    wm_ratio: wmRatio,
    stowage_factor: stowageFactor,
    cargo_density: cargoDensity,
    revenue_ton: round(Math.max(totalGross, totalVol), 3),
    total_gross_kg: totalGross,
    total_volumetric_weight_kg: totalVol,
    total_cbm: totalCbm,
  };
}

export function resolveLogisticsProfile(
  api: Partial<LogisticsProfile> | null | undefined,
  forwarderRows: ForwarderRow[],
): LogisticsProfile {
  const computed = computeLogisticsProfileFromForwarder(forwarderRows);
  if (!api) return computed;
  return {
    wm_ratio: api.wm_ratio ?? computed.wm_ratio,
    stowage_factor: api.stowage_factor ?? computed.stowage_factor,
    cargo_density: api.cargo_density ?? computed.cargo_density,
    revenue_ton: api.revenue_ton ?? computed.revenue_ton,
    total_gross_kg: api.total_gross_kg ?? computed.total_gross_kg,
    total_volumetric_weight_kg:
      api.total_volumetric_weight_kg ?? computed.total_volumetric_weight_kg,
    total_cbm: api.total_cbm ?? computed.total_cbm,
  };
}

export function forwarderTableColumns(rows: ForwarderRow[]): string[] {
  if (!rows.length) return [...FORWARDER_DISPLAY_COLUMNS];
  const fromData = Object.keys(rows[0]).filter((k) => !k.startsWith("_"));
  const ordered = FORWARDER_DISPLAY_COLUMNS.filter((c) => fromData.includes(c));
  const extras = fromData.filter((c) => !(ordered as string[]).includes(c));
  return [...ordered, ...extras];
}

function formatNumber(value: unknown, decimals: number): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value ?? "");
  return n.toFixed(decimals);
}

export function formatForwarderCell(col: string, row: ForwarderRow): string {
  const raw = row[col];
  if (isForwarderSubtotalRow(row) && isForwarderDimColumn(col)) {
    if (col === "箱子长(cm)") {
      if (typeof raw === "string" && raw.includes("方数:")) return raw;
      const cbm = row._subtotal_cbm ?? 0;
      return formatSubtotalCbmLabel(Number(cbm));
    }
    return "";
  }

  if (raw === null || raw === undefined || raw === "") return "";

  if (isForwarderSubtotalRow(row)) {
    if (col === "箱数") return String(Math.round(Number(raw)));
    if (col === "总实重(kg)") return formatNumber(raw, 2);
    if (col === "总体积重(kg)") return formatNumber(raw, 3);
    return String(raw);
  }

  if (col === "箱数") return String(Math.round(Number(raw)));
  if (col === "单件实重(kg)") return formatNumber(raw, 3);
  if (col === "总实重(kg)" || col === "单箱体积重(kg)" || col === "单箱实重(kg)") return formatNumber(raw, 2);
  if (col === "总体积重(kg)") return formatNumber(raw, 3);
  if (typeof raw === "number") return Number.isInteger(raw) ? String(raw) : formatNumber(raw, 2);
  return String(raw);
}

export function shouldSkipForwarderCell(col: string, row: ForwarderRow): boolean {
  return isForwarderSubtotalRow(row) && (col === "箱子宽(cm)" || col === "箱子高(cm)");
}

export function forwarderDimColSpan(row: ForwarderRow): number | undefined {
  return isForwarderSubtotalRow(row) ? FORWARDER_DIM_COLUMNS.length : undefined;
}
