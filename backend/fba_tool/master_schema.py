"""S2 表结构（方案 v8 §3.2 / 规则清单 §6.2），PRAGMA user_version = 3。

只 CREATE IF NOT EXISTS，不 DROP，不改老数据。
- hs_declare_template：按 品类+HS 配置申报要素模板（宠物类预置，钓具不预置，E4）
- fba_warehouse：FBA 仓库地址库（琪珞模板「！」表约 476 条，界面导入）
- customs_rule_profile：报关规则（净重、口岸、委托书有效期、征免性质、运费/日期留空）
- forwarder_template：货代模板（send / jiufang 首期；qiluo 保留现状；legacy 不做）
- shipment_ticket：票级数据（腾讯表格 / 运费测算表 / 九方单箱数据导入）
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

SCHEMA_VERSION = 3

PET_TEMPLATES = (
    # 来源：历史报关样例 JUS13DD21 / JUS15DD5 申报要素!I10
    {"category": "pet", "hs_code": "6307909000", "customs_name": "宠物垫",
     "elements_pattern": "1|2|{用途}|品牌：{品牌}牌|型号：{型号}", "default_purpose": "宠物用",
     "default_material": "", "declare_unit": "", "source": "历史报关样例 JUS13DD21"},
    {"category": "pet", "hs_code": "7326909000", "customs_name": "车载狗栏",
     "elements_pattern": "1|2|非工业用宠物车载用|铁制|焊接|品牌：{品牌}牌|型号：{型号}", "default_purpose": "非工业用宠物车载用",
     "default_material": "铁制", "declare_unit": "", "source": "历史报关样例 JUS15DD5"},
    # S3：golden 回归发现宠物台阶没有模板（回落成“宠物用品”），按历史样例补
    {"category": "pet", "hs_code": "3921199090", "customs_name": "宠物台阶",
     "elements_pattern": "1|2|{用途}|品牌：{品牌}牌|型号：{型号}", "default_purpose": "宠物用",
     "default_material": "", "declare_unit": "", "source": "历史报关样例 JUS2DAN11 / JUS2MD11"},
)

DEFAULT_RULE_PROFILE = {
    "name": "default",
    "net_weight_mode": "minus_per_box",
    "net_minus_per_box": 0.2,
    "net_ratio": None,
    "total_price_rule": "rounded_unit_price_x_qty",
    "loading_port": "宁波北仑",
    "entrust_valid_until_rule": "year_end",
    "exemption_nature": "101",
    "transport_mode": "海路运输",
    "fill_freight": 0,
    "fill_export_declare_date": 0,
    "forwarder_gross_tolerance_kg": 0.5,
    "is_default": 1,
}

FORWARDERS = (
    {"forwarder_id": "send", "status": "active", "merge_rule": "box_range", "price_basis": "declared", "gross_basis": "invoice_box_weight"},
    {"forwarder_id": "jiufang", "status": "active", "merge_rule": "sku_sum", "price_basis": "declared", "gross_basis": "measured_box_weight"},
    {"forwarder_id": "qiluo", "status": "frozen", "merge_rule": "", "price_basis": "", "gross_basis": ""},
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_v3(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS hs_declare_template (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            hs_code TEXT NOT NULL,
            customs_name TEXT,
            elements_pattern TEXT NOT NULL,
            default_purpose TEXT,
            default_material TEXT,
            declare_unit TEXT,
            brand_type TEXT DEFAULT '自主品牌',
            export_preferential TEXT DEFAULT '出口货物不能确定在最终目的国（地区）享受优惠关税',
            quarantine_code TEXT,
            source TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(category, hs_code)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS fba_warehouse (
            code TEXT PRIMARY KEY,
            name TEXT,
            company TEXT,
            address1 TEXT,
            address2 TEXT,
            address3 TEXT,
            city TEXT,
            state TEXT,
            zip TEXT,
            country TEXT,
            region TEXT,
            phone TEXT,
            source TEXT,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS customs_rule_profile (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            net_weight_mode TEXT,
            net_minus_per_box REAL,
            net_ratio REAL,
            total_price_rule TEXT,
            loading_port TEXT,
            entrust_valid_until_rule TEXT,
            exemption_nature TEXT,
            transport_mode TEXT,
            fill_freight INTEGER DEFAULT 0,
            fill_export_declare_date INTEGER DEFAULT 0,
            forwarder_gross_tolerance_kg REAL DEFAULT 0.5,
            is_default INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS forwarder_template (
            forwarder_id TEXT PRIMARY KEY,
            template_file TEXT,
            merge_rule TEXT,
            price_basis TEXT,
            gross_basis TEXT,
            status TEXT,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS shipment_ticket (
            fba_id TEXT PRIMARY KEY,
            batch TEXT,
            ticket_no TEXT,
            order_no TEXT,
            declare_mode TEXT,
            warehouse_code TEXT,
            region TEXT,
            forwarder TEXT,
            channel TEXT,
            lcl_no TEXT,
            box_count INTEGER,
            total_qty INTEGER,
            gross_kg REAL,
            net_kg REAL,
            chargeable_kg REAL,
            unit_freight REAL,
            total_freight REAL,
            etd TEXT,
            eta_expected TEXT,
            delivered_at TEXT,
            amazon_received_at TEXT,
            export_date TEXT,
            declare_date TEXT,
            invoice_date TEXT,
            contract_date TEXT,
            shipment_deadline TEXT,
            entrust_date TEXT,
            boxes_json TEXT,
            field_source_json TEXT,
            updated_at TEXT NOT NULL
        )"""
    )
    now = _now()
    for t in PET_TEMPLATES:
        conn.execute(
            """INSERT OR IGNORE INTO hs_declare_template
               (category, hs_code, customs_name, elements_pattern, default_purpose, default_material, declare_unit, source, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (t["category"], t["hs_code"], t["customs_name"], t["elements_pattern"], t["default_purpose"],
             t["default_material"], t["declare_unit"], t["source"], now),
        )
    # S3-fix2：旧库补列（货代毛重差异提示容差，默认 0.5 kg）
    cols = {r[1] for r in conn.execute("PRAGMA table_info(customs_rule_profile)").fetchall()}
    if "forwarder_gross_tolerance_kg" not in cols:
        conn.execute("ALTER TABLE customs_rule_profile ADD COLUMN forwarder_gross_tolerance_kg REAL DEFAULT 0.5")
    p = DEFAULT_RULE_PROFILE
    conn.execute(
        """INSERT OR IGNORE INTO customs_rule_profile
           (name, net_weight_mode, net_minus_per_box, net_ratio, total_price_rule, loading_port, entrust_valid_until_rule,
            exemption_nature, transport_mode, fill_freight, fill_export_declare_date, is_default, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (p["name"], p["net_weight_mode"], p["net_minus_per_box"], p["net_ratio"], p["total_price_rule"], p["loading_port"],
         p["entrust_valid_until_rule"], p["exemption_nature"], p["transport_mode"], p["fill_freight"],
         p["fill_export_declare_date"], p["is_default"], now),
    )
    for f in FORWARDERS:
        conn.execute(
            "INSERT OR IGNORE INTO forwarder_template (forwarder_id, merge_rule, price_basis, gross_basis, status, updated_at) VALUES (?,?,?,?,?,?)",
            (f["forwarder_id"], f["merge_rule"], f["price_basis"], f["gross_basis"], f["status"], now),
        )
