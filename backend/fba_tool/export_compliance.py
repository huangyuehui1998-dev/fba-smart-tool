"""导出发票前的报关与币种检查。

型号看产品库原值，不用 invoice_fields 里缺省的「无」。
采购价人民币，零售价美元。汇率只记录，不改货代模板里的币种下拉。
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Tuple

SIX_FIELDS = (
    ("chinese_name", "品名"),
    ("material", "材质"),
    ("purpose", "用途"),
    ("brand", "品牌"),
    ("model_name", "型号"),
    ("hs_code", "HS"),
)


def attach_compliance(model: Any, products: Dict[str, Dict[str, Any]], declaration_date: str) -> None:
    blockers, trace = review_products(products, declaration_date)
    meta = getattr(model, "meta", None)
    if isinstance(meta, dict):
        meta["fx"] = trace
    if blockers:
        from fba_tool.invoice_rules import InvoiceBlocked

        raise InvoiceBlocked(blockers)


def review_products(products: Dict[str, Dict[str, Any]], declaration_date: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    blockers: List[Dict[str, Any]] = []
    for sku, product in (products or {}).items():
        if not isinstance(product, dict):
            continue
        for key, label in SIX_FIELDS:
            if not str(_raw(product, key) or "").strip():
                blockers.append({
                    "code": "customs_field_missing",
                    "sku": sku,
                    "field": key,
                    "message": f"{sku} 缺少报关字段 {label}",
                })
        cost = str(product.get("product_cost_currency") or product.get("cost_currency") or "CNY").strip().upper()
        if cost not in {"CNY", "RMB", "¥"}:
            blockers.append({
                "code": "cost_currency_mismatch",
                "sku": sku,
                "field": "product_cost_currency",
                "message": f"{sku} 采购成本币种必须是人民币，当前是 {cost}",
            })
        retail = str(product.get("listing_price_currency") or product.get("retail_currency") or "USD").strip().upper()
        if retail != "USD":
            blockers.append({
                "code": "retail_currency_mismatch",
                "sku": sku,
                "field": "listing_price_currency",
                "message": f"{sku} 零售价必须是美元，当前是 {retail}",
            })
    return blockers, fx_trace(declaration_date)


def fx_trace(declaration_date: str) -> Dict[str, Any]:
    from fba_tool.fx_rates import snapshot_for_declaration

    when = declaration_date or date.today().isoformat()
    snap = snapshot_for_declaration(when, pair="USD/CNY", rate_type="customs_monthly")
    if not snap:
        return {
            "fx_source": "未换算（未配置当月海关汇率，成本人民币与申报美元未做折算）",
            "fx_publish_date": "",
            "fx_rate": None,
            "fx_applicable_month": when[:7],
            "fx_pair": "USD/CNY",
        }
    return {
        "fx_source": snap.get("fx_source") or snap.get("fx_source_url") or "",
        "fx_publish_date": snap.get("fx_publish_date") or "",
        "fx_rate": snap.get("fx_rate"),
        "fx_applicable_month": snap.get("fx_applicable_month") or "",
        "fx_pair": "USD/CNY",
        "fx_rate_type": snap.get("fx_rate_type") or "customs_monthly",
    }


def _raw(product: Dict[str, Any], key: str) -> Any:
    inv = _invoice(product)
    if key == "material":
        return product.get("material") or product.get("material_cn") or inv.get("material") or ""
    if key == "purpose":
        return product.get("purpose") or product.get("purpose_cn") or inv.get("purpose") or ""
    if key == "model_name":
        return product.get("model_name") if product.get("model_name") not in (None, "") else (inv.get("model") or "")
    if key == "hs_code":
        return inv.get("dest_hs_code") or product.get("hs_code") or ""
    return product.get(key) or ""


def _invoice(product: Dict[str, Any]) -> Dict[str, Any]:
    extra = dict(product.get("extra") or {})
    ed = product.get("extra_data")
    if isinstance(ed, str) and ed.strip():
        try:
            ed = json.loads(ed)
        except ValueError:
            ed = {}
    if isinstance(ed, dict):
        extra = {**ed, **extra}
    inv = dict(extra.get("invoice") or {})
    inv.update(product.get("invoice") or {})
    return inv
