/**
 * 全局业务常量 — 与后端 settings.py / user_settings 默认值对齐。
 * 用户可在侧边栏「系统设置」覆盖抛重系数、重量上限等可调参数。
 */

/** 默认抛重系数 (cm³ → kg) */
export const DEFAULT_THROW_RATIO = 6000;

/** 默认单箱毛重预警上限 (kg)，超重提示用；FBA 红线见 FBA_MAX_STANDARD_GROSS_* */
export const DEFAULT_WEIGHT_LIMIT_KG = 22.5;

/** FBA 标准件单箱毛重上限 (lbs) */
export const FBA_MAX_STANDARD_GROSS_LB = 50;

/** FBA 外箱单边长度上限 (in) */
export const FBA_MAX_SIDE_IN = 25;

/** Step 1 录入预览 debounce (ms) */
export const PREVIEW_DEBOUNCE_MS = 400;

/** Step 2 排箱明细同步 debounce (ms) */
export const BOX_EDITOR_SYNC_DEBOUNCE_MS = 450;
