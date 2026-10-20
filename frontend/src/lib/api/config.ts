import { apiFetchJson, apiPostJson, apiPutJson } from "@/lib/api/client";

export type UserParameters = {
  amazon_max_boxes?: number;
  weight_limit_kg?: number;
  max_mixed_items_per_box?: number;
  throw_ratio?: number;
  volume_divisor?: number;
  kg_to_lb_factor?: number;
  inch_to_cm_factor?: number;
  internal_gross_lb_factor?: number;
  sta_box_prefix?: string;
  factory_data_start_row?: number;
  factory_box_label_prefix?: string;
  forwarder_data_start_row?: number;
  input_template_blank_rows?: number;
  price_max?: number;
  [key: string]: unknown;
};

export type UserSettings = {
  parameters: UserParameters;
  factory_warehouse_columns?: Record<string, string>;
  forwarder_column_map?: Record<string, number>;
};

export type UserFormulas = Record<string, Record<string, string>>;

export function fetchUserSettings() {
  return apiFetchJson<UserSettings>("/api/config/settings");
}

export function saveUserSettings(settings: UserSettings) {
  return apiPutJson<{ ok: boolean; settings: UserSettings }>("/api/config/settings", { settings });
}

export function fetchUserFormulas() {
  return apiFetchJson<UserFormulas>("/api/config/formulas");
}

export function saveUserFormulas(formulas: UserFormulas) {
  return apiPutJson<{ ok: boolean; formulas: UserFormulas }>("/api/config/formulas", { formulas });
}

export function resetUserConfig() {
  return apiPostJson<{
    ok: boolean;
    settings: UserSettings;
    formulas: UserFormulas;
  }>("/api/config/reset", {});
}
