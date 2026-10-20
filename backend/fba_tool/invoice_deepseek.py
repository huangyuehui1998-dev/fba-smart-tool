"""DeepSeek API：发票地址解析 + 报关字段推理。"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import requests

from fba_tool.deepseek_billing import DeepseekUsageAccumulator
from fba_tool.deepseek_config import resolve_deepseek_options

DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

ADDRESS_SYSTEM = """你是物流地址解析助手。将亚马逊 FBA 仓库地址文本解析为 JSON。
只返回 JSON 对象，不要 markdown。字段：邮编, 国家代码, 省州代码, 城市, 地址。
国家代码默认 US（若文本为美国地址）。"""

CUSTOMS_SYSTEM = """你是一个专业的亚马逊跨境物流报关员。请根据我提供的 SKU 和产品简述，结合历史申报经验，输出报关所需的详细信息。
只返回 JSON 对象，不要 markdown。字段：海关编码, 中文品名, 英文品名, 材料, 用途, 品牌, 单个货值。
单个货值为数字。"""

HEADER_OPTIONS_SYSTEM = """你是跨境货代发票助手。根据货件上下文，为发票头部选项字段填写合理默认值。
只返回 JSON 对象，不要 markdown。仅返回用户请求的字段，不要额外字段。
常见惯例：是否包税→是；交货方式→海运；是否买保险→否；贸易术语→DDP。"""


def _api_key(api_key: str | None) -> str:
    key = (api_key or os.environ.get("DEEPSEEK_API_KEY", "")).strip()
    if not key:
        raise ValueError("未配置 DeepSeek API Key。")
    return key


def _chat(
    system: str,
    user: str,
    api_key: str,
    model: str | None = None,
    temperature: float | None = None,
    usage_acc: Optional[DeepseekUsageAccumulator] = None,
) -> dict:
    resolved_model, resolved_temp = resolve_deepseek_options(model, temperature)
    payload = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": resolved_temp,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    body = resp.json()
    usage = body.get("usage") or {}
    if usage_acc is not None:
        usage_acc.add(
            resolved_model,
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
        )
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def parse_address_with_ai(
    address_text: str,
    api_key: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    usage_acc: Optional[DeepseekUsageAccumulator] = None,
) -> Dict[str, Any]:
    key = _api_key(api_key)
    prompt = (
        f'请将以下亚马逊仓库地址文本解析为 JSON：{{"邮编": "", "国家代码": "US", "省州代码": "", "城市": "", "地址": ""}}\n\n'
        f"地址文本：{address_text}"
    )
    data = _chat(ADDRESS_SYSTEM, prompt, key, model=model, temperature=temperature, usage_acc=usage_acc)
    if isinstance(data, dict):
        return data
    return {}


def infer_customs_fields(
    product_names: List[str],
    history: dict,
    api_key: str | None = None,
    missing_keys: List[str] | None = None,
    known_values: Dict[str, Any] | None = None,
    model: str | None = None,
    temperature: float | None = None,
    usage_acc: Optional[DeepseekUsageAccumulator] = None,
) -> Dict[str, Any]:
    key = _api_key(api_key)
    all_keys = ["海关编码", "中文品名", "英文品名", "材料", "用途", "品牌", "单个货值"]
    keys = missing_keys or all_keys
    keys = [k for k in keys if k in all_keys]
    if not keys:
        return {}

    hist_text = json.dumps(history.get("categories", []), ensure_ascii=False, indent=2)
    names = "；".join(product_names[:10])
    known = known_values or {}
    known_text = json.dumps({k: known[k] for k in known if known.get(k) not in (None, "")}, ensure_ascii=False)
    key_template = ", ".join(f'"{k}": ""' for k in keys)
    user_prompt = (
        f"历史参考数据：\n{hist_text}\n\n"
        f"已从本地产品信息表获取：{known_text or '（无）'}\n\n"
        f"本次货件产品名称：{names}。\n"
        f"请仅补全以下空缺字段并校验已有字段是否合理，以 JSON 返回：{{{key_template}}}\n"
        f"不要修改或重复返回已有字段。"
    )
    data = _chat(CUSTOMS_SYSTEM, user_prompt, key, model=model, temperature=temperature, usage_acc=usage_acc)
    if not isinstance(data, dict):
        return {}
    return {k: data[k] for k in keys if k in data and data[k] not in (None, "")}


def infer_header_options_with_ai(
    field_keys: List[str],
    context: Dict[str, Any],
    api_key: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    usage_acc: Optional[DeepseekUsageAccumulator] = None,
) -> Dict[str, Any]:
    """发票顶部选项标签（包税/交货方式等）AI 推理，仅补 header_defaults 未覆盖的字段。"""
    keys = [k for k in field_keys if k]
    if not keys:
        return {}
    key = _api_key(api_key)
    ctx_text = json.dumps(context, ensure_ascii=False, indent=2)
    key_template = ", ".join(f'"{k}": ""' for k in keys)
    user_prompt = (
        f"货件上下文：\n{ctx_text}\n\n"
        f"请为以下发票头部选项字段填写合理默认值，以 JSON 返回：{{{key_template}}}"
    )
    data = _chat(HEADER_OPTIONS_SYSTEM, user_prompt, key, model=model, temperature=temperature, usage_acc=usage_acc)
    if not isinstance(data, dict):
        return {}
    return {k: data[k] for k in keys if k in data and data[k] not in (None, "")}
