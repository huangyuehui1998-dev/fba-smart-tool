"""S2 产品库新增字段与字段归属。

新增列（init_master_db 增量迁移，PRAGMA user_version=2）：
- listing_price / listing_price_currency / listing_price_at：亚马逊实时售价（领星 listing_price），申报价来源（v8 E1）
- declare_unit：申报单位（报关单位，如 件/个/套）
- field_source_json：每个字段的来源 {field: lingxing|manual|carton_import}

规则：
- 手填（manual）过的字段锁定，领星（lingxing）写入时跳过；
- 申报价：S2 初版是“手填 > 领星售价”，已被 D-01（2026-10-16）改为领星 listing_price 第一、手填第二，
  再由 D-12 修订为促销期（比正常价低 PROMO_THRESHOLD=5% 以上）按正常价 regular_price / NONPROMO_WINDOW_DAYS=90 天内非促销价申报；
  以 resolve_declared_price 的 docstring 为准。
- S8 新增列：regular_price / regular_price_at / last_nonpromo_price / last_nonpromo_at（D-12）。
- S9-step4 新增列：last_nonpromo_origin（D-15，self_first / confirmed / legacy）；领星常规价只在 regular_price_at
  起 90 天内有效（D-16），升级前没有采集时间的旧值以迁移时间为起点。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

SOURCE_LINGXING = "lingxing"
SOURCE_MANUAL = "manual"
SOURCE_CARTON_IMPORT = "carton_import"
SOURCES = (SOURCE_LINGXING, SOURCE_MANUAL, SOURCE_CARTON_IMPORT)

NEW_COLUMNS = {
    "listing_price": "REAL",
    "listing_price_currency": "TEXT",
    "listing_price_at": "TEXT",
    "declare_unit": "TEXT",
    "carton_gross_weight": "REAL",  # 单箱重（含箱，kg；v8 E2 九方单箱重含箱子）
    "field_source_json": "TEXT",
    "local_name": "TEXT",  # 领星本地品名（不覆盖报关中文品名 chinese_name）
    "listing_price_basis": "TEXT",  # 售价取自领星哪个字段：listing_price / price / landed_price
    "category": "TEXT",  # 品类：pet / fishing …（空 = 老数据，按 pet）
    # D-12（S8）：促销识别用的“正常价”
    "regular_price": "REAL",        # 领星 erp_listing.regular_price（常规价）
    "regular_price_at": "TEXT",
    "last_nonpromo_price": "REAL",  # 最近一次“非促销”时的实时售价（领星没给常规价时的兜底）
    "last_nonpromo_at": "TEXT",
    # S9-step4（D-15）：近 90 天非促销价的来源。ADD COLUMN 带默认值：升级前已有的记录、以及旧版 exe 之后写的记录都是 legacy（算“有历史”）
    "last_nonpromo_origin": "TEXT DEFAULT 'legacy'",
    "product_cost_cny": "REAL",
    "product_cost_currency": "TEXT",
    "retail_source": "TEXT",
    "retail_synced_at": "TEXT",
    "local_sku": "TEXT",
    "fee_fba_est": "REAL",
    "fee_referral_rate": "REAL",
    "listing_price_site": "TEXT",
}
ORIGIN_SELF_FIRST = "self_first"  # 首次同步、当时没有任何参照时自己记下的（可能就是促销价），不算“有历史”
ORIGIN_CONFIRMED = "confirmed"    # 之后的同步在有参照时记下的非促销价，或用户人工确认的正常价
ORIGIN_LEGACY = "legacy"          # 升级前已有的记录（无法区分来源），算“有历史”
HISTORY_HINT_TEXT = "无促销前历史价，申报价可能偏低，请人工确认"
from fba_tool.master_schema import SCHEMA_VERSION  # noqa: E402  v3：新增配置表

# 可由本模块写入的字段及类型
_FLOAT_FIELDS = (
    "listing_price", "declared_value", "qty_per_box", "product_cost_cny",
    "carton_length", "carton_width", "carton_height", "carton_weight", "carton_gross_weight",
    "regular_price", "fee_fba_est", "fee_referral_rate",
)
_TEXT_FIELDS = (
    "listing_price_currency", "declare_unit", "fnsku", "asin", "local_name", "listing_price_basis", "category",
    "product_cost_currency", "retail_source", "retail_synced_at", "local_sku", "listing_price_site",
)
WRITABLE_FIELDS = _FLOAT_FIELDS + _TEXT_FIELDS
# 这些字段由本模块直接写列（upsert_product 不认识）
OWN_FIELDS = (
    "listing_price", "listing_price_currency", "declare_unit", "carton_gross_weight", "local_name", "listing_price_basis",
    "category", "regular_price", "product_cost_cny", "product_cost_currency", "retail_source", "retail_synced_at",
    "local_sku", "fee_fba_est", "fee_referral_rate", "listing_price_site",
)
# 用户 2026-10-16 定：申报价按实时售价报，领星售价不受手填锁定
NEVER_LOCKED_FOR_LINGXING = ("listing_price", "listing_price_currency", "listing_price_basis", "regular_price")

# ---------------------------------------------------------------- D-12：促销期按正常价申报
PROMO_THRESHOLD = 0.05      # 实时售价比正常价低 5% 以上（不含正好 5%）才算促销；小于 5% 的调价按实时价报
NONPROMO_WINDOW_DAYS = 90   # “最近非促销价”只在 90 天内有效，过期就不再拿来比
PRICE_BASIS_PRIMARY = "listing_price"


def migrate(conn) -> None:
    cols = {str(r[1]) for r in conn.execute("PRAGMA table_info(product_master)").fetchall()}
    for name, typ in NEW_COLUMNS.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE product_master ADD COLUMN {name} {typ}")
    # S9-step4（D-16）：升级前没有采集时间的领星常规价，以迁移时间作为采集时间起点（只补空值，重复执行不变）
    conn.execute(
        "UPDATE product_master SET regular_price_at = ? "
        "WHERE regular_price IS NOT NULL AND COALESCE(regular_price_at, '') = ''",
        (_now(),),
    )
    from fba_tool.master_schema import ensure_v3

    ensure_v3(conn)
    _migrate_legacy_product_cost(conn)
    ver = conn.execute("PRAGMA user_version").fetchone()[0]
    if ver < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


OLD_PRODUCT_COST_NOTE = "产品成本→declared_value（CNY）"
NEW_PRODUCT_COST_NOTE = "产品成本→product_cost_cny（CNY）"


def _migrate_legacy_product_cost(conn) -> None:
    """把曾经写进 declared_value 的产品成本迁到 product_cost_cny，并记一条历史。"""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS product_field_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT,
            field TEXT,
            old_value TEXT,
            new_value TEXT,
            reason TEXT,
            created_at TEXT
        )"""
    )
    rows = conn.execute(
        "SELECT sku, declared_value, extra_data FROM product_master WHERE extra_data LIKE ?",
        (f"%{OLD_PRODUCT_COST_NOTE}%",),
    ).fetchall()
    now = _now()
    for sku, declared, extra in rows:
        if declared in (None, ""):
            continue
        conn.execute(
            """UPDATE product_master
               SET product_cost_cny = ?, product_cost_currency = 'CNY', declared_value = NULL,
                   extra_data = REPLACE(extra_data, ?, ?)
               WHERE sku = ?""",
            (declared, OLD_PRODUCT_COST_NOTE, NEW_PRODUCT_COST_NOTE, sku),
        )
        conn.execute(
            """INSERT INTO product_field_history (sku, field, old_value, new_value, reason, created_at)
               VALUES (?, 'product_cost_cny', ?, ?, ?, ?)""",
            (sku, str(declared), str(declared), OLD_PRODUCT_COST_NOTE, now),
        )


def _utcnow() -> datetime:
    """当前 UTC 时间（单独一个函数，测试可以固定它来测窗口边界）。"""
    return datetime.now(timezone.utc)


def _now() -> str:
    return _utcnow().isoformat()


def _clean_value(field: str, value: Any) -> Any:
    if field in _FLOAT_FIELDS:
        if value in (None, ""):
            raise ValueError(f"「{field}」不能为空")
        try:
            d = Decimal(str(value).strip())
        except InvalidOperation:
            raise ValueError(f"「{field}」不是有效数字：{value}")
        if d <= 0:
            raise ValueError(f"「{field}」必须大于 0：{value}")
        if field == "qty_per_box" and d != d.to_integral_value():
            raise ValueError(f"「{field}」必须是整数：{value}")
        return float(d)
    text = str(value or "").strip()
    if field == "category":
        text = text.lower()
    if not text:
        raise ValueError(f"「{field}」不能为空")
    return text


def get_field_sources(sku: str) -> Dict[str, str]:
    from fba_tool.master_db import _connect, resolve_stored_sku

    with _connect() as conn:
        stored = resolve_stored_sku(sku, conn) or str(sku or "").strip()  # S9-step3：统一匹配
        row = conn.execute("SELECT field_source_json FROM product_master WHERE sku = ?", (stored,)).fetchone()
    if not row or not row[0]:
        return {}
    try:
        data = json.loads(row[0])
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def set_product_fields(sku: str, values: Dict[str, Any], source: str) -> Dict[str, Any]:
    """按来源写字段并记录 field_source_json。领星不覆盖手填字段。返回 {changed, skipped_locked}。"""
    from fba_tool.master_db import _connect, get_product_by_sku, resolve_stored_sku, upsert_product

    key = str(sku or "").strip()
    if not key:
        raise ValueError("SKU 不能为空")
    # S9-step3：先匹配到库里原样存储的那条（保留原始写法）；以前只差大小写时 UPDATE 按原样比对，会静默什么都不写
    key = resolve_stored_sku(key) or key
    if source not in SOURCES:
        raise ValueError(f"未知来源：{source}")
    clean: Dict[str, Any] = {}
    for field, value in values.items():
        if field not in WRITABLE_FIELDS:
            raise ValueError(f"不允许写入的字段：{field}")
        clean[field] = _clean_value(field, value)

    if not get_product_by_sku(key):
        upsert_product({"sku": key})
    sources = get_field_sources(key)
    existing = get_product_by_sku(key) or {}
    changed: List[str] = []
    skipped: List[str] = []
    sets: Dict[str, Any] = {}
    for field, value in clean.items():
        if source == SOURCE_LINGXING and sources.get(field) == SOURCE_MANUAL and field not in NEVER_LOCKED_FOR_LINGXING:
            skipped.append(field)
            continue
        old = existing.get(field)
        if old in ("", None) or str(old) != str(value):
            changed.append(field)
        sets[field] = value
        sources[field] = source
    if "listing_price" in sets:
        sets["listing_price_at"] = _now()
        _track_nonpromo(sets, existing)
    if "regular_price" in sets:
        sets["regular_price_at"] = _now()
    if sets:
        sets["field_source_json"] = json.dumps(sources, ensure_ascii=False, sort_keys=True)
        sets["updated_at"] = _now()
        cols = ", ".join(f"{k} = ?" for k in sets)
        with _connect() as conn:
            conn.execute(f"UPDATE product_master SET {cols} WHERE sku = ?", (*sets.values(), key))
            conn.commit()
    return {"changed": changed, "skipped_locked": skipped}


def mark_field_sources(sku: str, fields: List[str], source: str) -> None:
    """只更新字段来源记录（字段值已由其他写入路径写好）。"""
    from fba_tool.master_db import _connect, resolve_stored_sku

    if source not in SOURCES:
        raise ValueError(f"未知来源：{source}")
    sku = resolve_stored_sku(sku) or str(sku or "").strip()  # S9-step3：统一匹配
    sources = get_field_sources(sku)
    for f in fields:
        sources[f] = source
    with _connect() as conn:
        conn.execute(
            "UPDATE product_master SET field_source_json = ? WHERE sku = ?",
            (json.dumps(sources, ensure_ascii=False, sort_keys=True), sku),
        )
        conn.commit()


def _track_nonpromo(sets: Dict[str, Any], existing: Dict[str, Any]) -> None:
    """D-12：记“最近非促销价”。本次实时价不低于正常价（常规价，没有就用上次非促销价）超过阈值时，视为非促销，记下来。"""
    lp = sets.get("listing_price")
    if lp in (None, ""):
        return
    lp = float(lp)
    # S8-fix2 N1：常规价 ≤ 本次售价视为“无信息”（实测领星 regular_price 等于售价），回退到近 90 天非促销价比较，
    # 防止促销价把上次记下的非促销价覆盖掉（例：16/16 再 12/12，16 不能被改成 12）。
    # S8-fix3/fix4（方案 A）：是否覆盖历史非促销价，用“有效常规价”和“近 90 天非促销价”中较大的那个比较：
    # 本次价 ≥ max×0.95 才更新，否则保留历史值（例：历史 16、售价 12、常规价 12.5 → 不覆盖 16）。申报正常价不用 max。
    # S9-step4（D-16）：常规价只在采集后 90 天内有效
    if "regular_price" in sets:
        reg = _informative_regular(sets.get("regular_price"), lp)
    else:
        reg = _recent_regular(existing, lp)
    recent = _recent_nonpromo(existing)
    ref = _max_ref(reg, recent)  # 是否更新非促销价：规则不变（D-12 方案 A），self_first 记录照样参与
    if ref is None or lp >= float(ref) * (1 - PROMO_THRESHOLD):
        sets["last_nonpromo_price"] = lp
        sets["last_nonpromo_at"] = _now()
        # S9-step4（D-15）：当时没有任何参照 → self_first（不算“有历史”）；有参照 → confirmed
        # S9-step4-fix3（D-15 修订）：self_first 不作为升级参照。升为 confirmed 的参照只能是本次有效的领星常规价，
        # 或 90 天窗口内来源为 confirmed / legacy 的非促销价记录；只有 self_first 可作参照时仍记 self_first。
        trusted = recent if recent is not None and last_nonpromo_origin(existing) != ORIGIN_SELF_FIRST else None
        sets["last_nonpromo_origin"] = ORIGIN_CONFIRMED if _max_ref(reg, trusted) is not None else ORIGIN_SELF_FIRST


def _informative_regular(rp: Any, listing_price: Optional[float]) -> Optional[float]:
    """S8-fix2 N1：常规价只有“高于当前售价”时才算有信息；≤ 售价（实测领星 regular_price 等于售价）当作没给，返回 None。"""
    if rp in (None, ""):
        return None
    try:
        v = float(rp)
    except (TypeError, ValueError):
        return None
    if not (v > 0) or v == float("inf"):  # 0、负数、NaN、inf 都当没给
        return None
    if listing_price is not None and v <= float(listing_price) + 1e-9:
        return None
    return v


def _max_ref(a: Optional[float], b: Optional[float]) -> Optional[float]:
    vals = [float(x) for x in (a, b) if x is not None]
    return max(vals) if vals else None


def _parse_at(at: Any) -> Optional[datetime]:
    if not at:
        return None
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t


def _in_window(at: Any) -> bool:
    from datetime import timedelta

    t = _parse_at(at)
    return t is not None and _utcnow() - t <= timedelta(days=NONPROMO_WINDOW_DAYS)


def _recent_nonpromo(master: Dict[str, Any]) -> Optional[float]:
    v, at = master.get("last_nonpromo_price"), master.get("last_nonpromo_at")
    if v in (None, "") or not at:
        return None
    if not _in_window(at):
        return None
    return float(v)


def regular_price_in_window(master: Optional[Dict[str, Any]]) -> bool:
    """S9-step4（D-16）：库里的领星常规价是否还在采集后 90 天内。没有采集时间的旧值按“迁移时已补成迁移时间”处理，
    运行时万一仍为空，视为刚采集（与迁移规则一致）。"""
    if not master or master.get("regular_price") in (None, ""):
        return False
    at = master.get("regular_price_at")
    if not at:
        return True
    return _in_window(at)


def _recent_regular(master: Optional[Dict[str, Any]], listing_price: Optional[float]) -> Optional[float]:
    """有信息（高于售价）且在 90 天窗口内的领星常规价；否则 None（D-12 / D-16）。"""
    if not master or not regular_price_in_window(master):
        return None
    return _informative_regular(master.get("regular_price"), listing_price)


def last_nonpromo_origin(master: Optional[Dict[str, Any]]) -> str:
    o = str((master or {}).get("last_nonpromo_origin") or "").strip()
    return o or ORIGIN_LEGACY


def has_price_history(master: Optional[Dict[str, Any]]) -> bool:
    """S9-step4（D-15）：90 天内有来源不是 self_first 的非促销价记录（confirmed / legacy）才算“有历史”。"""
    if not master or _recent_nonpromo(master) is None:
        return False
    return last_nonpromo_origin(master) != ORIGIN_SELF_FIRST


def price_history_hint(master: Optional[Dict[str, Any]]) -> str:
    """S9-step4（D-15）：没有有效的领星常规价、也没有“有历史”的非促销价记录时，返回提示文字；否则空串。
    只是提示，不改申报价（D-12）；不建议用 list_price / history_price（D-13）。"""
    if not master:
        return ""
    lp = master.get("listing_price")
    try:
        lpf = float(lp) if lp not in (None, "") else None
    except (TypeError, ValueError):
        lpf = None
    if lpf is None or not (lpf > 0):
        return ""  # 没有售价时另有“没有有效申报价”的提示
    if _recent_regular(master, lpf) is not None:
        return ""
    if has_price_history(master):
        return ""
    return HISTORY_HINT_TEXT


def normal_price(master: Optional[Dict[str, Any]]) -> Tuple[Optional[float], str]:
    """D-12 正常价：① 领星常规价 regular_price（须高于售价，≤ 售价视为无信息）② 近 90 天最近一次非促销实时价。
    不用划线价 list_price（亚马逊 List Price，常是虚高的建议零售价，实测 38.97 vs 售价 15.99）。"""
    if not master:
        return None, ""
    lp = master.get("listing_price")
    # S9-step4（D-16）：领星常规价只在采集后 90 天内有效；超期当作没有常规价，回退到近 90 天非促销价
    rp = _recent_regular(master, None if lp in (None, "") else float(lp))
    rn = _recent_nonpromo(master)
    if rn is not None and rn <= 0:
        rn = None
    # S8-fix4 N9（方案 A，按 D-12 原文）：有信息的常规价优先；没有时才用近 90 天非促销价。较大值只用于 _track_nonpromo 是否覆盖历史。
    if rp is not None:
        return rp, "lingxing_regular"
    if rn is not None and rn > 0:
        return rn, "lingxing_recent_nonpromo"
    return None, ""


def promo_info(master: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """领星实时售价处于促销（比正常价低 5% 以上）时返回 {listing_price, normal_price, normal_source, drop_pct}，否则 None。"""
    if not master:
        return None
    lp = master.get("listing_price")
    basis = str(master.get("listing_price_basis") or "").strip() or PRICE_BASIS_PRIMARY
    if lp in (None, "") or basis != PRICE_BASIS_PRIMARY:
        return None
    normal, src = normal_price(master)
    if normal is None:
        return None
    lp = float(lp)
    if lp < normal * (1 - PROMO_THRESHOLD) - 1e-9:
        return {"listing_price": lp, "normal_price": normal, "normal_source": src,
                "drop_pct": round((normal - lp) / normal * 100, 1)}
    return None


def _valid_price(v: Any) -> Optional[float]:
    """有限正数、且不超过 price_max()（设置参数 price_max，出厂 100000）才算有效价格；其余返回 None。
    S9-step2-fix2 N1/N2：字符串走统一的 parse_price（逗号只认标准千分位，不接受科学计数法）；
    库里的数字不再四舍五入（保持原值），只检查范围。"""
    import math

    from fba_tool.lingxing_adapter import parse_price, price_max

    if v in (None, "") or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) and 0 < f <= price_max() else None
    return parse_price(v)


def listing_price_eligible_for_us_declared(master: Optional[Dict[str, Any]]) -> bool:
    """美国站申报能否采用这条售价。

    站点和币种都空：历史行仍按 D-01 采用 listing_price（导入当时没写这两列）。
    站点明确不是美国，或币种明确不是 USD：不能当成美国站申报价。
    空币种不在这里当成 USD；零售导入和同步在写入前就跳过。
    """
    if not master:
        return False
    site = str(master.get("listing_price_site") or "").strip()
    if site:
        from fba_tool.declared_value import is_target_site

        if not is_target_site(site, site):
            return False
    raw = master.get("listing_price_currency")
    if raw in (None, ""):
        return True
    from fba_tool.lingxing_adapter import normalize_currency

    try:
        code = normalize_currency(raw)
    except ValueError:
        return False
    return code == "USD"


def resolve_declared_price(master: Optional[Dict[str, Any]]) -> Tuple[Optional[float], str]:
    """申报价（用户 2026-10-16 定，按实时售价报；D-12 修订：促销期按正常价）：
    1. 领星 listing_price（来源 lingxing）；若比正常价低 5% 以上（促销），改报正常价
       （来源 lingxing_regular = 领星常规价 / lingxing_recent_nonpromo = 近 90 天非促销价）
    2. 手填 declared_value（来源 manual）——只在领星没有 listing_price 时用
    3. 领星 price / landed_price 兜底（来源 lingxing_price / lingxing_landed_price）
    4. 旧 declared_value（来源 legacy，需警告）

    目标申报站是美国。listing_price_site 不是美国，或 listing_price_currency 不是 USD 时，
    这条售价不进入上面的 1/3（含促销正常价），接着看手填 / 旧申报价。
    """
    if not master:
        return None, ""
    sources = master.get("field_sources") or {}
    lp = _valid_price(master.get("listing_price"))  # S9-step2-fix A3：0、负数、NaN、inf、非数字都当没有售价，不申报 0/NaN
    if not listing_price_eligible_for_us_declared(master):
        lp = None
    master = dict(master, listing_price=lp)  # 无效或非美国站售价 → None；字符串 → 解析后的数
    basis = str(master.get("listing_price_basis") or "").strip() or PRICE_BASIS_PRIMARY
    if lp not in (None, "") and basis == PRICE_BASIS_PRIMARY:
        promo = promo_info(master)  # D-12（修订 D-01）：促销期按正常价申报，并提示
        if promo:
            return promo["normal_price"], promo["normal_source"]
        return float(lp), SOURCE_LINGXING
    dv = master.get("declared_value")
    if dv not in (None, "") and sources.get("declared_value") == SOURCE_MANUAL:
        return float(dv), SOURCE_MANUAL
    if lp not in (None, ""):
        return float(lp), f"lingxing_{basis}"
    if dv not in (None, ""):
        return float(dv), "legacy"
    return None, ""


def confirm_normal_price(sku: str, price: Any, note: str = "") -> Dict[str, Any]:
    """S9-step4（D-15）：用户人工确认正常价。按 parse_price + 价格上限校验，写成近 90 天非促销价（origin=confirmed），
    并写审计日志（app_data/logs/price_confirm_audit.log，一行一条 JSON）。之后 S9-B 提示消失。
    SKU 不在产品库 → LookupError；只差大小写的多条 → SkuCaseConflict；价格无效 → ValueError（带原值和原因）。"""
    from fba_tool.lingxing_adapter import parse_price_reason
    from fba_tool.master_db import _connect, get_product_by_sku, resolve_stored_sku

    key = resolve_stored_sku(sku)
    if not key:
        raise LookupError(f"SKU 不在产品库：{str(sku or '').strip()}（请先确认写入产品库）")
    num, reason = parse_price_reason(price)
    if num is None:
        raise ValueError(f"正常价“{str(price)[:40]}”无效：{reason or '为空'}")
    before = get_product_by_sku(key) or {}
    now = _now()
    with _connect() as conn:
        conn.execute(
            "UPDATE product_master SET last_nonpromo_price = ?, last_nonpromo_at = ?, last_nonpromo_origin = ?, "
            "updated_at = ? WHERE sku = ?",
            (num, now, ORIGIN_CONFIRMED, now, key),
        )
        conn.commit()
    _audit("confirm_normal_price", {
        "sku": key,
        "input": str(price)[:40],
        "price": num,
        "listing_price": before.get("listing_price"),
        "old_last_nonpromo_price": before.get("last_nonpromo_price"),
        "old_last_nonpromo_at": before.get("last_nonpromo_at") or "",
        "old_origin": last_nonpromo_origin(before) if before.get("last_nonpromo_price") not in (None, "") else "",
        "note": str(note or "")[:200],
    })
    after = get_product_by_sku(key) or {}
    return {"sku": key, "price": num, "origin": ORIGIN_CONFIRMED, "at": now,
            "history_hint": price_history_hint(after)}


def _audit(action: str, data: Dict[str, Any]) -> None:
    """审计日志：app_data/logs/price_confirm_audit.log（追加，一行一条 JSON；不含密钥）。"""
    from fba_tool.app_paths import logs_dir

    path = logs_dir() / "price_confirm_audit.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"time": _now(), "action": action, **data}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
