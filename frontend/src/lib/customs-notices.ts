export const DECLARED_VALUE_CFR_NOTE =
  "按 19 CFR 141.86，非购买发货应申报出口国批发价值；按零售价申报属于高报（海关风险低，但税负偏高）";

export const NET_WEIGHT_MODE_NOTICE =
  "默认净重口径已改为毛重 − 箱皮重（tare_from_carton）；原 ratio 口径仍可在设置中切换";

export const DECLARED_VALUE_BASES = [
  { value: "retail", label: "零售价 retail" },
  { value: "fob", label: "FOB" },
  { value: "cost", label: "采购成本 cost" },
] as const;

export const NET_WEIGHT_MODES = [
  { value: "tare_from_carton", label: "毛重 − 箱皮重（规范）" },
  { value: "minus_per_box", label: "每箱扣固定皮重" },
  { value: "ratio", label: "比例法（非规范口径）" },
] as const;
