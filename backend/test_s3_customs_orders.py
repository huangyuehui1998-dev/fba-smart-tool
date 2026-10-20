"""S3-3 订单号、分组、文件名、一致性校验（方案 v8 §3.6、§5-7 文件名）。"""
from __future__ import annotations

import pytest

from fba_tool import customs_package as cp
from fba_tool.customs_export import CustomsExportBlocked, export_blockers
from fba_tool.customs_package import (
    build_customs_from_tickets,
    consistency_checks,
    customs_filename,
    declare_mode_for,
    suggest_order_no,
)

PROFILE = {"id": "t", "name": "测试公司", "credit_code": "X", "signed_at": "武汉", "domestic_source": "武汉"}
PET = {"chinese_name": "宠物垫", "hs_code": "6307909000", "unit": "包", "brand": "DemoBrand", "category": "pet"}


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ad = tmp_path / "ad"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    from fba_tool.master_db import init_master_db

    init_master_db()
    monkeypatch.setattr(cp, "_catalog_hints", lambda sku: {})


def _t(sid, wh="SBD1", boxes=(10, 10), qty=8):
    return {"shipment_id": sid, "warehouse": wh, "boxes": list(boxes), "lines": [dict(PET, sku="A", qty=qty, unit_price=39.99)]}


@pytest.mark.parametrize("batch,code,boxes,suffix,expect", [
    (13, "DD", 21, "", "JUS13DD21"), ("13", "DD", 32, "LAX", "JUS13DD32LAX"), (5, "HB", 171, "", "JUS5HB171"),
])
def test_suggest_order_no(batch, code, boxes, suffix, expect):
    assert suggest_order_no(batch, code, boxes, suffix) == expect


def test_suggest_order_no_default_code_by_fba_count():
    assert suggest_order_no(14, None, 12, fba_count=1) == "JUS14DD12"
    assert suggest_order_no(5, None, 171, fba_count=5) == "JUS5HB171"


@pytest.mark.parametrize("n,override,expect", [(1, "", "单独"), (2, "", "合并"), (1, "合并", "合并"), (3, "单独", "单独")])
def test_declare_mode(n, override, expect):
    assert declare_mode_for([f"F{i}" for i in range(n)], override) == expect


@pytest.mark.parametrize("ids,override,fmt,expect", [
    (["FBA19RJH13MS"], "", "xlsx", "JUS14DD12-FBA19RJH13MS-单独报关-9810-报关资料.xlsx"),
    (["F1", "F2"], "", "xls", "JUS14DD12-合并报关-9810-报关资料.xls"),
    (["FBA19P4NX8HH"], "合并", "xls", "JUS14DD12-FBA19P4NX8HH-合并报关-9810-报关资料.xls"),
])
def test_filename(ids, override, fmt, expect):
    assert customs_filename("JUS14DD12", ids, fmt, override) == expect


def test_filename_rejects_bad_format():
    with pytest.raises(ValueError):
        customs_filename("X", ["F"], "csv")


def test_data_carries_shipment_ids_and_mode():
    d = build_customs_from_tickets([_t("F1"), _t("F2", "LAX9")], PROFILE, order_no="JUS1HB4")
    assert d.shipment_ids == ["F1", "F2"] and d.declare_mode == "合并"
    d1 = build_customs_from_tickets([_t("F1")], PROFILE, order_no="JUS1DD2", overrides={"declare_mode": "合并"})
    assert d1.declare_mode == "合并"


def _codes(issues):
    return {i["code"] for i in issues}


def test_consistency_ok():
    assert consistency_checks(build_customs_from_tickets([_t("F1")], PROFILE, order_no="JUS1DD2")) == []


def test_pieces_must_be_integer():
    d = build_customs_from_tickets([_t("F1")], PROFILE, order_no="JUS1DD2")
    d.total_pieces = "5箱"
    assert "pieces_not_int" in _codes(consistency_checks(d))


def test_gross_ge_net():
    d = build_customs_from_tickets([_t("F1")], PROFILE, order_no="JUS1DD2")
    d.total_net_kg = d.total_gross_kg + 1
    assert "net_gt_gross" in _codes(consistency_checks(d))


def test_qty_and_boxes_match_lines():
    d = build_customs_from_tickets([_t("F1")], PROFILE, order_no="JUS1DD2")
    d.total_qty = 9
    d.total_pieces = 3
    assert {"qty_mismatch", "pieces_mismatch"} <= _codes(consistency_checks(d))


def test_remarks_order_must_match_contract():
    d = build_customs_from_tickets([_t("F1")], PROFILE, order_no="JUS2MX33")
    d.remarks = "订单编号：JUS2DAN11。仓库编码：TOL3。FBA编码：F1。"
    assert "remarks_order_mismatch" in _codes(consistency_checks(d))


def test_order_no_required():
    d = build_customs_from_tickets([_t("F1")], PROFILE, order_no="")
    assert "order_no_missing" in _codes(consistency_checks(d))


def test_order_no_duplicate_against_tickets():
    from fba_tool.ticket_import import set_ticket_fields

    set_ticket_fields("FBA19OTHER01", {"order_no": "JUS1DD2"}, "tencent")
    set_ticket_fields("FBA19MINE001", {"order_no": "JUS1DD2"}, "tencent")
    d = build_customs_from_tickets([_t("FBA19MINE001")], PROFILE, order_no="JUS1DD2")
    issues = consistency_checks(d)
    assert "order_no_duplicate" in _codes(issues) and "FBA19OTHER01" in issues[0]["message"]
    d2 = build_customs_from_tickets([_t("FBA19MINE001"), _t("FBA19OTHER01")], PROFILE, order_no="JUS1DD2")
    assert "order_no_duplicate" not in _codes(consistency_checks(d2))


def test_export_blockers_include_consistency():
    d = build_customs_from_tickets([_t("F1")], PROFILE, order_no="JUS1DD2")
    d.total_net_kg = 999
    assert any("净重" in b for b in export_blockers(d))
