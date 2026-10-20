/** Step 2 排箱 / Step 3 导出 相关类型契约。 */
import type { ApiSkuRow } from "@/types/step1";

export interface BoxEditorApiRow {
  箱号: number;
  来源: string;
  SKU简称: string;
  数量: number;
}

export interface BoxMetricRow {
  箱号: number;
  SKU种类: number;
  件数: number;
  "净重(kg)": number;
  "毛重(kg)": number;
  "体积(cm3)": number;
  超重: boolean;
  FBA毛重违规?: boolean;
  FBA超大件豁免?: boolean;
}

export type FbaCartonSideWarning = {
  sku: string;
  side_label: string;
  side_cm: number;
  max_side_cm: number;
  limit_cm: number;
  limit_in: number;
  message: string;
};

export type FbaBoxGrossViolation = {
  box_no: number;
  gross_kg: number;
  limit_kg: number;
  limit_lb: number;
  exempt_oversize_single: boolean;
  source?: "amazon" | "internal" | string;
  message: string;
};

export type FbaBoxCountWarning = {
  box_count: number;
  limit: number | null;
  level?: string;
  source?: "amazon" | "internal" | string;
  message: string;
};

export type PolicyFinding = {
  box_no?: number;
  level?: string;
  source?: "amazon" | "internal" | string;
  source_type?: string | null;
  message: string;
};

export type FbaCompliance = {
  blocked: boolean;
  limits: {
    max_standard_gross_kg: number;
    max_standard_gross_lb: number;
    max_side_cm: number;
    max_side_in: number;
    max_boxes_per_shipment: number;
    fee_disclaimer?: string;
  };
  carton_side_warnings: FbaCartonSideWarning[];
  box_gross_violations: FbaBoxGrossViolation[];
  box_count_warning: FbaBoxCountWarning | null;
  policy_findings?: PolicyFinding[];
  summary_lines: string[];
  side_warning_count: number;
  gross_violation_count: number;
};

export interface TailPoolRow {
  SKU简称: string;
  待排尾数: number;
  "单个重量(kg)": number;
}

export interface WorkflowPayload {
  rows: ApiSkuRow[];
  box_editor: BoxEditorApiRow[];
  fnsku_overrides?: Record<string, string>;
  transport_mode?: string;
  confirm_weight_warnings?: boolean;
}

export interface CalculateBoxesResponse {
  box_editor: BoxEditorApiRow[];
  tail_pool: TailPoolRow[];
  metrics: BoxMetricRow[];
  has_overweight: boolean;
  fba_compliance: FbaCompliance;
  has_fba_block: boolean;
}

export interface BoxMetricsResponse {
  metrics: BoxMetricRow[];
  has_overweight: boolean;
  weight_limit_kg: number;
  fba_compliance: FbaCompliance;
  has_fba_block: boolean;
}

export interface Step3PreviewResponse {
  matrix: Record<string, unknown>[];
  box_count: number;
  sku_count: number;
}
