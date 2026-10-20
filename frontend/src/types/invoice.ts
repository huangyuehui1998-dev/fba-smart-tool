/** Step 4.5 货代发票 相关类型契约。 */

export interface InvoiceCellFill {
  cell: string;
  value: string;
  source: string;
  field_key?: string;
  required?: boolean;
  /** 清空区单元格：只擦除内容，不覆盖背景色 */
  clear?: boolean;
}

export interface InvoiceGridRow {
  字段: string;
  值: string;
  来源: string;
  单元格: string;
  必填: string;
}

export interface InvoiceDraftResponse {
  shipment_id: string;
  warehouse_code: string;
  template_sheet: string;
  grid?: InvoiceGridRow[];
  cells: InvoiceCellFill[];
  missing_required: string[];
  template_base64?: string;
  template_hash?: string;
  phase?: "preview" | "filled";
  total_tokens?: number;
  estimated_cost_rmb?: number;
  revenue_ton?: number;
  wm_ratio?: string;
  warnings?: string[];
}

export interface InvoicePreviewResponse {
  shipment_id: string;
  warehouse_code: string;
  template_sheet: string;
  grid: InvoiceGridRow[];
  missing_required: string[];
  template_base64?: string;
  template_hash?: string;
  phase: "preview";
}
