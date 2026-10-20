import type { MasterProduct } from "@/lib/api/master-data";
import type { ApiComputedRow, ApiSkuRow } from "@/lib/api/step1";

export interface Row {
  sku: string;
  fnsku: string;
  totalQty: string;
  perBox: string;
  l: string;
  w: string;
  h: string;
  unitKg: string;
  emptyKg: string;
  grossKg: string;
  /** official = 主库外箱 carton_*；manual = 运营手填外箱 */
  dataSource?: "official" | "manual";
}

export interface ComputedDisplay {
  fullBoxes: string;
  remainder: string;
  netKg: string;
  grossTotalKg: string;
}

export const EMPTY_ROW: Row = {
  sku: "",
  fnsku: "",
  totalQty: "",
  perBox: "",
  l: "",
  w: "",
  h: "",
  unitKg: "",
  emptyKg: "",
  grossKg: "",
};

function cellStr(v: unknown): string {
  if (v === null || v === undefined || v === "") return "";
  return String(v);
}

function cellNum(v: unknown): number | string {
  if (v === null || v === undefined || v === "") return 0;
  return v as number | string;
}

export function rowToApi(row: Row): ApiSkuRow {
  return {
    SKU简称: row.sku.trim(),
    FNSKU: row.fnsku.trim(),
    发货总数: cellNum(row.totalQty),
    单箱装量: cellNum(row.perBox),
    "箱长(cm)": cellNum(row.l),
    "箱宽(cm)": cellNum(row.w),
    "箱高(cm)": cellNum(row.h),
    "单个重量(kg)": cellNum(row.unitKg),
    "空纸箱重(kg)": cellNum(row.emptyKg),
    "单箱毛重(kg)": row.grossKg.trim() === "" ? null : cellNum(row.grossKg),
  };
}

export function rowsToApi(rows: Row[]): ApiSkuRow[] {
  return rows.map(rowToApi);
}

export function apiRowToRow(api: ApiSkuRow): Row {
  return {
    sku: cellStr(api.SKU简称),
    fnsku: cellStr(api.FNSKU),
    totalQty: cellStr(api.发货总数),
    perBox: cellStr(api.单箱装量),
    l: cellStr(api["箱长(cm)"]),
    w: cellStr(api["箱宽(cm)"]),
    h: cellStr(api["箱高(cm)"]),
    unitKg: cellStr(api["单个重量(kg)"]),
    emptyKg: cellStr(api["空纸箱重(kg)"]),
    grossKg: cellStr(api["单箱毛重(kg)"]),
  };
}

export function apiRowsToRows(apiRows: ApiSkuRow[]): Row[] {
  if (!apiRows.length) return [{ ...EMPTY_ROW }];
  return apiRows.map(apiRowToRow);
}

export function computedFromApi(api: ApiComputedRow): ComputedDisplay {
  const full = api.预计整箱数;
  const rem = api.尾数;
  const net = api["预计总净重(kg)"];
  const gross = api["预计总毛重(kg)"];
  return {
    fullBoxes: full === null || full === undefined || full === "" ? "—" : String(full),
    remainder: rem === null || rem === undefined || rem === "" ? "—" : String(rem),
    netKg: net === null || net === undefined || net === "" ? "—" : Number(net).toFixed(3),
    grossTotalKg: gross === null || gross === undefined || gross === "" ? "—" : Number(gross).toFixed(3),
  };
}

export function emptyComputed(): ComputedDisplay {
  return { fullBoxes: "—", remainder: "—", netKg: "—", grossTotalKg: "—" };
}

export function mergeRowWithMaster(row: Row, product?: MasterProduct | null): Row {
  const sku = row.sku.trim();
  if (!sku || !product) {
    return { ...row, dataSource: sku ? "manual" : undefined };
  }
  const hasCarton =
    Number(product.carton_length) > 0 &&
    Number(product.carton_width) > 0 &&
    Number(product.carton_height) > 0;
  return {
    ...row,
    fnsku: product.fnsku || row.fnsku,
    ...(hasCarton
      ? {
          l: String(product.carton_length ?? row.l),
          w: String(product.carton_width ?? row.w),
          h: String(product.carton_height ?? row.h),
          dataSource: "official" as const,
        }
      : { dataSource: "manual" as const }),
  };
}

export function rowsEquivalent(a: Row[], b: Row[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) {
    const x = a[i];
    const y = b[i];
    if (
      x.sku !== y.sku ||
      x.fnsku !== y.fnsku ||
      x.l !== y.l ||
      x.w !== y.w ||
      x.h !== y.h ||
      x.unitKg !== y.unitKg ||
      x.dataSource !== y.dataSource
    ) {
      return false;
    }
  }
  return true;
}

export function aggregateTotals(computed: ComputedDisplay[]) {
  let totalFullBoxes = 0;
  let totalNet = 0;
  let totalGross = 0;

  for (const c of computed) {
    const full = Number(c.fullBoxes);
    const rem = Number(c.remainder);
    if (!Number.isNaN(full)) {
      totalFullBoxes += full + (rem > 0 ? 1 : 0);
    }
    const net = Number(c.netKg);
    const gross = Number(c.grossTotalKg);
    if (!Number.isNaN(net)) totalNet += net;
    if (!Number.isNaN(gross)) totalGross += gross;
  }

  return { totalFullBoxes, totalNet, totalGross };
}

export {
  DEEPSEEK_KEY_STORAGE,
  getDeepseekApiKey,
  getDeepseekModel,
  getDeepseekTemperature,
  getDeepseekOptions,
} from "@/lib/deepseek-settings";
