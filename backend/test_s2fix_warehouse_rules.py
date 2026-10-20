"""S2-fix 第4/7项：fba_warehouse 导入（琪珞「！」表）、customs_rule_profile、产品信息表初始导入（临时库）、仓库白名单。"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fba_tool import warehouse_codes as wc
from fba_tool.master_db import init_master_db, list_products
from fba_tool.warehouse_db import (
    apply_warehouse_import,
    get_default_rule_profile,
    get_warehouse,
    list_warehouse_codes,
    parse_warehouse_sheet,
    preview_warehouse_import,
    update_rule_profile,
)

HERE = Path(__file__).parent
WH_FILE = HERE / "tests" / "fixtures" / "warehouse" / "fba_warehouse_qiluo.xlsx"
PRODUCT_INFO = HERE / "tests" / "fixtures" / "product-info" / "宠物庭院-产品信息表(仅内部人员使用).xlsx"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    return ad


def test_parse_qiluo_sheet_about_476_rows():
    rows, errors = parse_warehouse_sheet(WH_FILE.read_bytes(), WH_FILE.name)
    assert 470 <= len(rows) <= 476
    by = {r["code"]: r for r in rows}
    assert by["ABE2"]["city"] == "Breinigsville" and by["ABE2"]["state"] == "PA" and by["ABE2"]["zip"] == "18031"
    assert by["ABE8"]["zip"] == "08518"          # 前导 0 不丢
    assert by["CVG3"]["state"] == "KY"           # Hebron, KY
    assert by["TOL3"]["state"] == "OH" and by["TOL3"]["region"] == "美中"
    assert by["ONT8"]["region"] == "美西"
    assert by["ABE2"]["region"] == "美东"
    assert by["HEA2"]["city"] == "BREINIGSVILLE"  # \xa0 清掉
    assert any(i["value"] == "HLI2" for i in errors)  # 重复代码给提示


def test_preview_then_apply_then_zero_diff():
    data = WH_FILE.read_bytes()
    pv = preview_warehouse_import(data, WH_FILE.name)
    assert pv["summary"]["new"] >= 470 and list_warehouse_codes() == []  # 预览不写库
    res = apply_warehouse_import(data, WH_FILE.name)
    assert res["written"] >= 470
    assert get_warehouse("LAX9")["state"] == "CA"
    pv2 = preview_warehouse_import(data, WH_FILE.name)
    assert pv2["summary"]["new"] == 0 and pv2["summary"]["changed"] == 0


def test_whitelist_removes_unverified_and_uses_table():
    assert "TOL2" not in wc.BUILTIN_WAREHOUSE_CODES and "DAY1" not in wc.BUILTIN_WAREHOUSE_CODES
    assert "CVG3" in wc.BUILTIN_WAREHOUSE_CODES
    assert "IUTI" not in wc.known_warehouse_codes()
    apply_warehouse_import(WH_FILE.read_bytes(), WH_FILE.name)
    assert "IUTI" in wc.known_warehouse_codes()   # fba_warehouse 表里的仓直接进白名单
    assert "TOL2" not in wc.known_warehouse_codes() and "DAY1" not in wc.known_warehouse_codes()
    assert "WALMART-LAX1" not in wc.known_warehouse_codes() and "MDT2-1" not in wc.known_warehouse_codes()
    from fba_tool.warehouse_db import get_warehouse as gw
    assert gw("WALMART-LAX1") is not None  # 地址库照样收录


def test_cvg3_listed_under_kentucky_comment():
    src = Path(wc.__file__).read_text(encoding="utf-8")
    ky = src.index("# KY")
    nxt = src.index("# ", ky + 4)
    assert '"CVG3"' in src[ky:nxt]
    assert src.count('"CVG3"') == 1


def test_rule_profile_seeded_and_editable():
    p = get_default_rule_profile()
    assert p["loading_port"] == "宁波北仑" and p["exemption_nature"] == "101"
    assert p["net_minus_per_box"] == 0.2 and p["fill_freight"] == 0 and p["fill_export_declare_date"] == 0
    update_rule_profile({"loading_port": "上海"})
    assert get_default_rule_profile()["loading_port"] == "上海"
    with pytest.raises(ValueError):
        update_rule_profile({"net_minus_per_box": -1})


def test_customs_defaults_follow_rule_profile():
    from fba_tool.customs_package import build_customs_data
    from test_customs_package import _sample_pair

    update_rule_profile({"loading_port": "上海"})
    d = build_customs_data([_sample_pair()], [], {"id": "t"}, source="shipment", order_no="T")
    assert d.loading_port == "上海"


@pytest.mark.skipif(not PRODUCT_INFO.is_file(), reason="无产品信息表样本")
def test_initial_import_product_info_into_temp_db():
    from main import app

    c = TestClient(app)
    with PRODUCT_INFO.open("rb") as f:
        r = c.post("/api/master-data/upload/product-info", files={"file": (PRODUCT_INFO.name, f)})
    assert r.status_code == 200 and r.json()["upserted"] > 0
    assert len(list_products()) == r.json()["total_in_db"]


def test_api_warehouse_import_and_list():
    from main import app

    c = TestClient(app)
    with WH_FILE.open("rb") as f:
        pv = c.post("/api/master-data/import/warehouses/preview", files={"file": (WH_FILE.name, f)})
    assert pv.status_code == 200 and pv.json()["summary"]["new"] >= 470
    with WH_FILE.open("rb") as f:
        ap = c.post("/api/master-data/import/warehouses/apply", files={"file": (WH_FILE.name, f)})
    assert ap.status_code == 200
    r = c.get("/api/master-data/warehouses", params={"q": "LAX9"})
    assert r.json()["items"][0]["code"] == "LAX9"
    bad = c.post("/api/master-data/import/warehouses/preview", files={"file": ("x.xlsx", b"not xlsx")})
    assert bad.status_code == 422
