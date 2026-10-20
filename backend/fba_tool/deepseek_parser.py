from __future__ import annotations

import json
import os
import re
from typing import List

import pandas as pd
import requests

from fba_tool.data_processing import INPUT_COLUMNS, empty_input_df
from fba_tool.deepseek_config import resolve_deepseek_options

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
SYSTEM_PROMPT = """你是亚马逊FBA发货数据解析助手。用户会粘贴自然语言或表格文本，请提取每条SKU的发货信息。
只返回 JSON 数组，不要 markdown。每个元素字段：
sku, total_qty, carton_qty, length_cm, width_cm, height_cm, unit_weight_kg, carton_tare_kg, carton_gross_kg
缺失数值用 null。单位必须是公制 cm/kg。"""


def parse_with_deepseek(
    raw_text: str,
    api_key: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> pd.DataFrame:
    key = (api_key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
    if not key:
        raise ValueError("未配置 DeepSeek API Key。请在侧边栏输入或设置环境变量 DEEPSEEK_API_KEY。")
    if not raw_text.strip():
        return empty_input_df()

    resolved_model, resolved_temp = resolve_deepseek_options(model, temperature)

    payload = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        "temperature": resolved_temp,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    rows = _normalize_payload(content)
    if not rows:
        return empty_input_df()
    return pd.DataFrame(rows, columns=INPUT_COLUMNS)


def _normalize_payload(content: str) -> List[dict]:
    data = json.loads(content)
    if isinstance(data, dict):
        for key in ("items", "data", "skus", "rows"):
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
        else:
            data = [data]
    if not isinstance(data, list):
        return []

    rows: List[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "SKU简称": _pick(item, ["sku", "SKU", "SKU简称", "sku_name"], ""),
                "FNSKU": _pick(item, ["fnsku", "FNSKU"], ""),
                "发货总数": _to_int(_pick(item, ["total_qty", "qty", "发货总数"], 0)),
                "单箱装量": _to_int(_pick(item, ["carton_qty", "单箱装量", "per_carton"], 0)),
                "箱长(cm)": _to_float(_pick(item, ["length_cm", "长", "箱长"], 0)),
                "箱宽(cm)": _to_float(_pick(item, ["width_cm", "宽", "箱宽"], 0)),
                "箱高(cm)": _to_float(_pick(item, ["height_cm", "高", "箱高"], 0)),
                "单个重量(kg)": _to_float(_pick(item, ["unit_weight_kg", "单个重量"], 0)),
                "空纸箱重(kg)": _to_float(_pick(item, ["carton_tare_kg", "空纸箱重"], 0)),
                "单箱毛重(kg)": _to_optional(_pick(item, ["carton_gross_kg", "单箱毛重"], None)),
            }
        )
    return [r for r in rows if str(r["SKU简称"]).strip()]


def _pick(item: dict, keys: List[str], default):
    for k in keys:
        if k in item and item[k] not in (None, ""):
            return item[k]
    return default


def _to_int(v) -> int:
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return 0
        return int(float(v))
    except Exception:
        return 0


def _to_float(v) -> float:
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return 0.0
        num = float(re.sub(r"[^\d.\-]", "", str(v)) or "0")
        return num
    except Exception:
        return 0.0


def _to_optional(v):
    if v is None or (isinstance(v, str) and not str(v).strip()):
        return None
    try:
        return float(v)
    except Exception:
        return None
