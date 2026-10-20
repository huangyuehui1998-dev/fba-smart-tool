"""品类 + HS 申报要素配置（hs_declare_template）与“缺报关配置”判定。

- 宠物类模板由 master_schema 预置（历史报关样例）；钓具不预置，等报关行确认后由用户录入（方案 Q13 / E4）。
- 产品 category 为空的老数据按 pet 处理（历史产品全是宠物类）。
- 非宠物品类缺模板：产品库标“缺报关配置”，导出阻断，不套用宠物模板。
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

LEGACY_DEFAULT_CATEGORY = "pet"
MISSING_LABEL = "缺报关配置"
_HS_RE = re.compile(r"^\d{8,10}$")
_TEMPLATE_FIELDS = (
    "customs_name", "elements_pattern", "default_purpose", "default_material", "declare_unit",
    "brand_type", "export_preferential", "quarantine_code", "source",
)


def effective_category(product: Optional[Dict[str, Any]]) -> str:
    return str((product or {}).get("category") or "").strip().lower() or LEGACY_DEFAULT_CATEGORY


def _rows(sql: str, args=()) -> List[Dict[str, Any]]:
    from fba_tool.master_db import _connect

    with _connect() as conn:
        cur = conn.execute(sql, args)
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


def list_hs_templates(category: Optional[str] = None) -> List[Dict[str, Any]]:
    if category:
        return _rows("SELECT * FROM hs_declare_template WHERE category = ? ORDER BY hs_code", (category.strip().lower(),))
    return _rows("SELECT * FROM hs_declare_template ORDER BY category, hs_code")


def get_hs_template(category: str, hs_code: str) -> Optional[Dict[str, Any]]:
    rows = _rows(
        "SELECT * FROM hs_declare_template WHERE category = ? AND hs_code = ?",
        (str(category or "").strip().lower(), str(hs_code or "").strip()),
    )
    return rows[0] if rows else None


def upsert_hs_template(rec: Dict[str, Any]) -> Dict[str, Any]:
    from fba_tool.master_db import _connect

    cat = str(rec.get("category") or "").strip().lower()
    hs = str(rec.get("hs_code") or "").strip()
    try:  # S8 D6：允许 9507.10.00 90 这类带点/空格的写法，统一成纯数字
        from fba_tool.hs_code import normalize_hs_code
        hs = normalize_hs_code(hs) or hs
    except Exception:
        pass
    pattern = str(rec.get("elements_pattern") or "").strip()
    if not cat:
        raise ValueError("品类不能为空")
    if not _HS_RE.match(hs):
        raise ValueError(f"HS 编码应为 8–10 位数字：{hs}")
    if not pattern:
        raise ValueError("申报要素模板不能为空")
    vals = {k: (str(rec.get(k)).strip() if rec.get(k) not in (None, "") else None) for k in _TEMPLATE_FIELDS}
    vals["elements_pattern"] = pattern
    now = datetime.now(timezone.utc).isoformat()
    cols = ", ".join(_TEMPLATE_FIELDS)
    marks = ", ".join("?" for _ in _TEMPLATE_FIELDS)
    upd = ", ".join(f"{k} = COALESCE(excluded.{k}, hs_declare_template.{k})" for k in _TEMPLATE_FIELDS)
    with _connect() as conn:
        conn.execute(
            f"""INSERT INTO hs_declare_template (category, hs_code, {cols}, updated_at) VALUES (?, ?, {marks}, ?)
                ON CONFLICT(category, hs_code) DO UPDATE SET {upd}, updated_at = excluded.updated_at""",
            (cat, hs, *[vals[k] for k in _TEMPLATE_FIELDS], now),
        )
        conn.commit()
    return get_hs_template(cat, hs) or {}


def render_elements(template: Dict[str, Any], values: Dict[str, Any]) -> str:
    """{用途}{品牌}{型号}{材质}{品名} 占位符替换；用途/材质空时取模板默认。"""
    fill = {
        "用途": str(values.get("用途") or template.get("default_purpose") or "").strip(),
        "材质": str(values.get("材质") or template.get("default_material") or "").strip(),
        "品牌": str(values.get("品牌") or "").strip() or "无",
        "型号": str(values.get("型号") or "").strip() or "无型号",
        "品名": str(values.get("品名") or template.get("customs_name") or "").strip(),
    }
    out = str(template.get("elements_pattern") or "")
    for k, v in fill.items():
        out = out.replace("{" + k + "}", v)
    return out


def customs_config_missing(product: Optional[Dict[str, Any]], templates: Optional[Dict[tuple, Dict[str, Any]]] = None) -> List[str]:
    """返回缺失项：hs_code / chinese_name / hs_declare_template。空列表 = 配置齐全。"""
    p = product or {}
    missing: List[str] = []
    hs = str(p.get("hs_code") or "").strip()
    if not hs:
        missing.append("hs_code")
    if not str(p.get("chinese_name") or "").strip():
        missing.append("chinese_name")
    cat = effective_category(p)
    if hs:
        tpl = templates.get((cat, hs)) if templates is not None else get_hs_template(cat, hs)
        if not tpl:
            missing.append("hs_declare_template")
    return missing


def all_templates_map() -> Dict[tuple, Dict[str, Any]]:
    return {(t["category"], t["hs_code"]): t for t in list_hs_templates()}
