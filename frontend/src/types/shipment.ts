/** Step 4 货件校验 相关类型契约。 */
import type { ActualPlacementFee } from "@/types/step1";

export type PackingMode = "amazon_led" | "strict_local";

export interface ShipmentBundle {
  shipment_id: string;
  warehouse: string;
  csv_base64: string;
  pdf_base64: string;
  /** Step 4 已解析货件结构，供 Step 4.5 复用，避免重解析 CSV */
  parsed_shipment?: Record<string, unknown>;
}

export interface BoxLabelMappingRow {
  本地箱号: string;
  本地箱序号: number;
  FBA箱号: string;
  亚马逊箱序号: number;
  目的仓: string;
  货件编号: string;
  装箱内容: string;
  匹配方式: string;
}

/** 申报给亚马逊的箱重/箱规与 Step 2 方案不符，存在重量差异费风险。 */
export interface DeclaredSpecWarning {
  kind: "weight" | "volume" | "total_weight";
  box: string;
  declared: number;
  planned: number;
  deviation_pct: number;
}

export interface ShipmentValidateResponse {
  ok: boolean;
  status_lines: string[];
  errors: string[];
  throw_ratio: number;
  mapping_ok?: boolean | null;
  box_label_mapping?: BoxLabelMappingRow[];
  actual_placement_fee?: ActualPlacementFee | null;
  packing_mode?: PackingMode;
  cross_check_ok?: boolean;
  declared_spec_warnings?: DeclaredSpecWarning[];
  worker_packing_ready?: boolean;
  worker_packing_preview?: Record<string, unknown>[];
  worker_packing_warehouses?: string[];
  shipping_sheet?: Record<string, unknown>[];
  shipping_sheet_legend?: Record<string, unknown>[];
  forwarder?: Record<string, unknown>[];
  shipments?: ShipmentBundle[];
  cargo_density?: number;
  stowage_factor?: number;
  wm_ratio?: string;
  revenue_ton?: number;
  total_net_kg?: number;
  total_gross_kg?: number;
  total_cbm?: number;
  total_volumetric_weight_kg?: number;
  warehouse_warnings?: {
    shipment_id: string;
    csv_code: string;
    pdf_code: string;
    message?: string;
  }[];
}
