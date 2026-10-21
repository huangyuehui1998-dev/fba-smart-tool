"""S2-3：领星 Listing 导出（Excel/CSV）导入产品库：先预览差异，确认后写入；手填字段不被覆盖。"""
from __future__ import annotations

import io

import openpyxl
import pytest
from fastapi.testclient import TestClient

from fba_tool.master_db import get_product_by_sku, init_master_db, patch_product_field
from fba_tool.product_import import apply_listing_import, preview_listing_import


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()


def _csv(rows, enc="utf-8-sig"):
    lines = ["MSKU,FNSKU,ASIN,价格"] + [",".join(r) for r in rows]
    return "\n".join(lines).encode(enc)


def _xlsx(rows):
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["MSKU", "FNSKU", "ASIN", "价格"])
    for r in rows:
        ws.append(r)
    b = io.BytesIO(); wb.save(b); return b.getvalue()


def test_preview_then_apply_then_zero_diff():
    data = _csv([["A", "X00TEST001", "B000000001", "15.99"], ["B", "X00TEST002", "B000000002", "37.99"]])
    pv = preview_listing_import(data, "listing.csv")
    assert pv["errors"] == []
    assert pv["summary"]["new"] == 2
    assert get_product_by_sku("A") is None          # 预览不写库
    res = apply_listing_import(data, "listing.csv")
    assert res["written"] == 2
    assert get_product_by_sku("A")["listing_price"] == 15.99
    pv2 = preview_listing_import(data, "listing.csv")
    assert pv2["summary"]["changed"] == 0 and pv2["summary"]["new"] == 0


def test_manual_field_not_overwritten():
    apply_listing_import(_csv([["A", "X00TEST001", "B000000001", "15.99"]]), "l.csv")
    patch_product_field("A", "fnsku", "X0MANUAL01")
    pv = preview_listing_import(_csv([["A", "X00TEST009", "B000000001", "15.99"]]), "l.csv")
    assert pv["summary"]["locked"] == 1
    apply_listing_import(_csv([["A", "X00TEST009", "B000000001", "15.99"]]), "l.csv")
    assert get_product_by_sku("A")["fnsku"] == "X0MANUAL01"


def test_bad_price_reported_by_row_and_gbk_xlsx():
    pv = preview_listing_import(_csv([["A", "X1", "B1", "abc"], ["", "X2", "B2", "9"]], enc="gbk"), "l.csv")
    rows = {(e["row"], e["field"]) for e in pv["errors"]}
    assert (2, "listing_price") in rows and (3, "sku") in rows
    pv = preview_listing_import(_xlsx([["A", "X00TEST001", "B000000001", 12.5]]), "l.xlsx")
    assert pv["summary"]["new"] == 1


def test_missing_required_header():
    with pytest.raises(ValueError, match="MSKU"):
        preview_listing_import("FNSKU,价格\nX1,1\n".encode(), "l.csv")


def test_api_preview_and_apply():
    from main import app
    c = TestClient(app)
    data = _csv([["A", "X00TEST001", "B000000001", "15.99"]])
    r = c.post("/api/master-data/import/listing/preview", files={"file": ("l.csv", data, "text/csv")})
    assert r.status_code == 200 and r.json()["summary"]["new"] == 1
    r = c.post("/api/master-data/import/listing/apply", files={"file": ("l.csv", data, "text/csv")})
    assert r.status_code == 200 and r.json()["written"] == 1
