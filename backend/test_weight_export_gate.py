"""P0-1：使用毛重的导出在未确认时 409，确认后 200。"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from fba_tool.customs_package import CustomsLineItem, CustomsPackageData
from fba_tool.master_db import init_master_db, upsert_product
from main import app

WARN_ROW = {
    "SKU简称": "TEST_A",
    "FNSKU": "X00TESTA1",
    "发货总数": 4,
    "单箱装量": 4,
    "箱长(cm)": 40,
    "箱宽(cm)": 30,
    "箱高(cm)": 30,
    "单个重量(kg)": 0,
    "空纸箱重(kg)": 0.3,
    "单箱毛重(kg)": 1.8,
}

STEP3 = {
    "rows": [WARN_ROW],
    "box_editor": [{"箱号": 1, "来源": "整箱", "SKU简称": "TEST_A", "数量": 4}],
}

CSV = "\n".join(
    [
        '"货件编号","FBATEST00001"',
        '"货件名称","TEST-CLT2"',
        '"配送地址","Charlotte, NC"',
        '"箱子数量","1"',
        "",
        '"单件商品（1 箱）"',
        '"SKU","商品名称","ASIN","FNSKU","状况","预处理类型","商品总数","箱子 1 的商品数量"',
        '"TEST_A","item","B0TEST0001","X00TESTA1","新品","无","4","4"',
        "",
        '"","","","","","","箱号","FBATEST00001U000001"',
        '"","","","","","","包装箱重量（磅）：","4"',
        '"","","","","","","包装箱长度（英寸）：","16"',
        '"","","","","","","包装箱宽度（英寸）：","12"',
        '"","","","","","","包装箱高度（英寸）：","12"',
    ]
).encode("utf-8")


@pytest.fixture()
def client(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    upsert_product(
        {
            "sku": "TEST_A",
            "fnsku": "X00TESTA1",
            "asin": "B0TEST0001",
            "english_name": "Item",
            "chinese_name": "物品",
            "brand": "B",
            "material": "铁",
            "purpose": "用",
            "model_name": "无",
            "listing_price": 10,
            "declared_value": 10,
            "hs_code": "7326909000",
            "extra_data": {"invoice": {"unit": "个", "material_en": "iron", "purpose_en": "use"}},
        }
    )
    return TestClient(app)


def _assert_gate(response_unconfirmed, response_confirmed):
    assert response_unconfirmed.status_code == 409, response_unconfirmed.text
    detail = response_unconfirmed.json()["detail"]
    assert detail["code"] == "WEIGHT_CONFIRM_REQUIRED"
    assert detail["items"]
    assert response_confirmed.status_code == 200, response_confirmed.text


def test_step3_sta_and_internal(client):
    for path in ("/api/export/step3/amazon", "/api/export/step3/internal"):
        blocked = client.post(path, json={**STEP3, "confirm_weight_warnings": False})
        allowed = client.post(path, json={**STEP3, "confirm_weight_warnings": True})
        _assert_gate(blocked, allowed)


def test_shipping_sheet_and_forwarder_and_worker(client):
    cases = [
        (
            "/api/export/shipping_sheet",
            {
                "shipping_sheet": [{"票数": "第一票", "仓库代码": "CLT2", "总数量": 4, "总毛重(KG)": 1.8}],
                "weight_rows": [WARN_ROW],
            },
        ),
        (
            "/api/export/forwarder",
            {
                "forwarder": [{"仓库代码": "CLT2", "箱数": 1, "发货总数": 4, "总实重(kg)": 1.8}],
                "weight_rows": [WARN_ROW],
            },
        ),
        (
            "/api/export/worker_packing_preview",
            {
                "worker_packing_preview": [{"纸箱编号": "1", "产品名称": "TEST_A", "FNSKU": "X00TESTA1", "数量": 4}],
                "weight_rows": [WARN_ROW],
            },
        ),
    ]
    for path, body in cases:
        blocked = client.post(path, json={**body, "confirm_weight_warnings": False})
        allowed = client.post(path, json={**body, "confirm_weight_warnings": True})
        _assert_gate(blocked, allowed)


def test_customs_export_gate(client):
    data = CustomsPackageData(
        order_no="T1",
        total_pieces=1,
        total_qty=4,
        total_gross_kg=1.8,
        total_net_kg=1.5,
        total_amount=40,
        lines=[
            CustomsLineItem(
                seq=1,
                chinese_name="物品",
                qty=4,
                unit_price=10,
                amount=40,
                box_count=1,
                gross_kg=1.8,
                net_kg=1.5,
            )
        ],
    ).to_dict()
    body = {"source": "shipment", "order_no": "T", "data": data, "weight_rows": [WARN_ROW]}
    blocked = client.post("/api/customs/export", json={**body, "confirm_weight_warnings": False})
    allowed = client.post("/api/customs/export", json={**body, "confirm_weight_warnings": True})
    _assert_gate(blocked, allowed)


def test_invoice_export_gate(client):
    files = {"csv_file": ("ship.csv", CSV, "text/csv")}
    blocked = client.post(
        "/api/invoice-export/export",
        data={"forwarder_id": "send", "confirm_weight_warnings": "false", "weight_rows": json.dumps([WARN_ROW])},
        files=files,
    )
    allowed = client.post(
        "/api/invoice-export/export",
        data={"forwarder_id": "send", "confirm_weight_warnings": "true", "weight_rows": json.dumps([WARN_ROW])},
        files={"csv_file": ("ship.csv", CSV, "text/csv")},
    )
    _assert_gate(blocked, allowed)
