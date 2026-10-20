/** Step 1 录入 / 预览 / 入库配置费 相关类型契约。 */

/** 与后端 INPUT_COLUMNS 对齐 */
export interface ApiSkuRow {
  SKU简称: string;
  FNSKU: string;
  发货总数: number | string;
  单箱装量: number | string;
  "箱长(cm)": number | string;
  "箱宽(cm)": number | string;
  "箱高(cm)": number | string;
  "单个重量(kg)": number | string;
  "空纸箱重(kg)": number | string;
  "单箱毛重(kg)": number | string | null;
}

export interface ApiComputedRow extends ApiSkuRow {
  预计整箱数?: number | string | null;
  尾数?: number | string | null;
  "预计总净重(kg)"?: number | string | null;
  "预计总毛重(kg)"?: number | string | null;
}

export interface ParseRowsResponse {
  count: number;
  rows: ApiSkuRow[];
  fnsku_overrides?: Record<string, string>;
}

export interface ComputePreviewResponse {
  rows: ApiComputedRow[];
  merged_rows?: ApiSkuRow[];
  data_sources?: string[];
  total_cbm: number;
  total_volumetric_weight: number;
  throw_ratio?: number;
  cargo_density?: number;
  stowage_factor?: number;
  wm_ratio?: string;
  revenue_ton?: number;
  total_net_kg?: number;
  total_gross_kg?: number;
  weight_warnings?: GrossWeightWarning[];
  cost_dashboard?: CostDashboard;
}

/** 录入单箱毛重与「装量×单件重+空箱重」不符，可能引发重量差异费。 */
export interface GrossWeightWarning {
  row_index: number;
  sku: string;
  declared_kg: number;
  expected_kg: number;
  diff_kg: number;
  deviation_pct: number;
  message: string;
}

export interface ValidationErrorItem {
  row_index: number;
  row_number: number;
  field: string;
}

export type PlacementFeeRange = {
  min_usd: number;
  max_usd: number;
};

export type PlacementOptionKey = "one_location" | "split_2_3";

export type PlacementLineItem = {
  sku: string;
  quantity: number;
  eligible: boolean;
  size_class: string | null;
  size_class_label: string;
  actual_lb: number;
  dimensional_lb: number | null;
  billing_lb: number;
  volume_weight_applied: boolean;
  split_2_3_disabled: boolean;
  split_2_3_disabled_reason: string | null;
  one_location: PlacementFeeRange | null;
  split_2_3: PlacementFeeRange | null;
  optimized_5: PlacementFeeRange;
  subtotal_one_location: PlacementFeeRange | null;
  subtotal_split_2_3: PlacementFeeRange | null;
  ineligible_reason?: string | null;
};

export type PlacementOptionSummary = {
  enabled: boolean;
  min_usd: number | null;
  max_usd: number | null;
  disabled_reason?: string | null;
};

export type PlacementSummary = {
  total_units: number;
  eligible_units: number;
  oversize_units: number;
  ineligible_units: number;
  line_items: PlacementLineItem[];
  one_location: PlacementFeeRange & { enabled: boolean };
  split_2_3: PlacementOptionSummary;
  optimized_5: PlacementFeeRange & { enabled: boolean };
};

export type ActualPlacementFee = {
  status: string;
  actual_location_count: number;
  actual_warehouses: string[];
  warehouse_regions: string[];
  scenario: string;
  scenario_label: string;
  step1_preview: {
    one_location: PlacementFeeRange & { enabled?: boolean };
    split_2_3: PlacementOptionSummary;
    optimized_5: PlacementFeeRange & { enabled?: boolean };
  };
  applicable_range_min_usd: number;
  applicable_range_max_usd: number;
  /** 区间中值，用于定价/毛利测算；locked_usd 是保守上限，只看它会高估成本 */
  applicable_range_mid_usd?: number;
  locked_usd: number;
  lock_method: string;
  eligible_units: number;
  total_units: number;
};

export type CostDashboard = {
  placement: PlacementSummary;
  actual_placement_fee?: ActualPlacementFee | null;
};

export interface ValidateInputResponse {
  valid: boolean;
  errors: ValidationErrorItem[];
}
