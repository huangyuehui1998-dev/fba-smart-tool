import { downloadBlob, apiFetchJson, apiPatchJson, apiPostJson, apiUpload } from "@/lib/api/client";

export type MasterProduct = {
  sku: string;
  asin: string;
  fnsku: string;
  unit_length: number | null;
  unit_width: number | null;
  unit_height: number | null;
  unit_weight: number | null;
  carton_length: number | null;
  carton_width: number | null;
  carton_height: number | null;
  carton_weight: number | null;
  chinese_name: string;
  model_name: string;
  english_name: string;
  hs_code: string;
  material: string;
  purpose: string;
  brand: string;
  declared_value: number | null;
  extra_data: string;
  updated_at: string;
  parent_asin?: string;
  sid?: number | null;
  listing_status?: string;
  fulfillment_channel?: string;
  lingxing_synced_at?: string;
  data_source?: string;
  category?: string;
  local_name?: string;
  listing_price?: number | null;
  declare_unit?: string;
  invoice_unit?: string;
  pcs_per_set?: number | null;
  purchase_price?: number | null;
  material_en?: string;
  purpose_en?: string;
  dest_hs_code?: string;
  fob_unit_value?: number | null;
  carton_gross_weight?: number | null;
  customs_config_missing?: string[];
  customs_config_status?: string;
};

export type MasterPatchableField = keyof Omit<MasterProduct, "sku" | "updated_at">;

export type MasterDataListResponse = {
  items: MasterProduct[];
  count: number;
  /** S9-step3：只差大小写/全角半角的 SKU 组（不自动合并，只提示） */
  sku_case_conflicts?: string[][];
};

export type MasterUploadResponse = {
  ok: boolean;
  report_type: string;
  parsed: number;
  upserted: number;
  total_in_db: number;
};

export type MasterProductInfoUploadResponse = {
  ok: boolean;
  parsed: number;
  upserted: number;
  total_in_db: number;
  column_map: Record<string, string>;
};

export type MasterResolveResponse = {
  flags: Record<string, "official" | "manual">;
  products: Record<string, MasterProduct>;
};

export type MasterLocalExcelOpenResponse = {
  ok: boolean;
  path: string;
  rows: number;
  message: string;
};

export type MasterLocalExcelSyncResponse = {
  ok: boolean;
  parsed: number;
  upserted: number;
  total_in_db: number;
  path: string;
};

export function fetchMasterDataList() {
  return apiFetchJson<MasterDataListResponse>("/api/master-data/list");
}

export function fetchMasterSku(sku: string) {
  return apiFetchJson<MasterProduct>(`/api/master-data/sku/${encodeURIComponent(sku)}`);
}

export function uploadMasterReport(file: File, reportType: "fee_preview" | "inventory") {
  const form = new FormData();
  form.append("file", file);
  form.append("report_type", reportType);
  return apiUpload<MasterUploadResponse>("/api/master-data/upload", form);
}

export function uploadMasterProductInfo(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiUpload<MasterProductInfoUploadResponse>("/api/master-data/upload/product-info", form);
}

export function updateCustomsRuleProfile(body: Record<string, unknown>) {
  return apiPostJson<Record<string, unknown>>("/api/master-data/customs-rule-profile", body);
}

export function fetchCustomsRuleProfile() {
  return apiFetchJson<Record<string, unknown>>("/api/master-data/customs-rule-profile");
}

export function uploadRetailPrices(file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiUpload<{
    parsed_count: number;
    imported_count: number;
    unmatched_count: number;
    warnings?: string[];
  }>("/api/master-data/retail-prices/upload", form);
}

export function patchMasterSkuField(sku: string, field: MasterPatchableField, value: unknown) {
  return apiPatchJson<MasterProduct>(`/api/master-data/sku/${encodeURIComponent(sku)}`, {
    field,
    value,
  });
}

export function deleteMasterSku(sku: string) {
  return apiFetchJson<{ ok: boolean; sku: string }>(
    `/api/master-data/sku/${encodeURIComponent(sku)}`,
    { method: "DELETE" },
  );
}

export function openLocalMasterExcel() {
  return apiFetchJson<MasterLocalExcelOpenResponse>("/api/master-data/local-excel/open");
}

export function syncLocalMasterExcel() {
  return apiPostJson<MasterLocalExcelSyncResponse>("/api/master-data/local-excel/sync", {});
}

export function resolveMasterSkus(skus: string[]) {
  return apiPostJson<MasterResolveResponse>("/api/master-data/resolve-skus", { skus });
}


export type WarehouseImportPreview = {
  summary: { new: number; changed: number; unchanged: number; total: number };
  issues: { row: number; field: string; value: string; message: string }[];
};

function warehouseForm(file: File) {
  const fd = new FormData();
  fd.append("file", file);
  return fd;
}

/** FBA 仓库地址库（琪珞发票模板「！」表）：先预览差异，确认后写入 */
export function previewWarehouseImport(file: File) {
  return apiUpload<WarehouseImportPreview>("/api/master-data/import/warehouses/preview", warehouseForm(file));
}

export function applyWarehouseImport(file: File) {
  return apiUpload<{ ok: boolean; written: number }>("/api/master-data/import/warehouses/apply", warehouseForm(file));
}


export type TicketImportPreview = {
  source: "tencent" | "freight" | "jiufang";
  summary: { new: number; changed: number; unchanged: number; total: number };
  issues: { row: number; field: string; value: string; message: string }[];
};

/** 票级数据（腾讯表格 / 运费测算表 / 九方单箱数据）：自动识别，先预览再写入 shipment_ticket */
export function previewTicketImport(file: File) {
  return apiUpload<TicketImportPreview>("/api/tickets/import/preview", warehouseForm(file));
}

export function applyTicketImport(file: File) {
  return apiUpload<{ ok: boolean; tickets: number; tickets_written: number }>("/api/tickets/import/apply", warehouseForm(file));
}


export type ProductEditPreview = {
  changes: { row: number; sku: string; field: string; old: unknown; new: unknown; source_before: string }[];
  errors: { row: number; sku: string; field: string; value: unknown; message: string }[];
  note: string;
};

/** 产品库导出 Excel（本地批量修改用，D-2026-10-16-03） */
export function exportMasterProducts() {
  return downloadBlob("/api/master-data/export.xlsx", "产品库.xlsx");
}

/** 导回本地改过的产品库：先预览改动字段，确认后写入（改动记 manual 并锁定） */
export function previewProductEdits(file: File) {
  return apiUpload<ProductEditPreview>("/api/master-data/import/edits/preview", warehouseForm(file));
}

export function applyProductEdits(file: File) {
  return apiUpload<ProductEditPreview & { written: number }>("/api/master-data/import/edits/apply", warehouseForm(file));
}

/** S9-step4（D-15）：人工确认正常价（默认是将要申报的价，可改）。写成 confirmed，S9-B 提示随之消失。 */
export async function confirmNormalPrice(sku: string, price: number | string) {
  return apiPostJson<{ ok: boolean; sku: string; price: number; origin: string; at: string; history_hint: string }>(
    `/api/master-data/sku/${encodeURIComponent(sku)}/confirm-normal-price`,
    { price },
  );
}
