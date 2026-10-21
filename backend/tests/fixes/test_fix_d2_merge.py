"""S1-fix1：D2 多张“待分配”票合并报关。"""
from __future__ import annotations

from pathlib import Path

import pytest

from fba_tool import customs_package as cp
from fba_tool.customs_package import build_customs_data
from fba_tool.shipment_parser import PdfShipment, parse_csv_shipment
from fba_tool.shipment_validator import ShipmentPair

TEST1 = Path(__file__).resolve().parents[3] / "test1"
FILES = [
    ("第一票ONT8.csv", "ONT8", 29),
    ("第二票AVP1.csv", "AVP1", 32),
    ("第三票MDW2.csv", "MDW2", 34),
    ("第四票LAX9.csv", "LAX9", 25),
    ("第五票TOL3.csv", "TOL3", 25),
]
PROFILE = {"id": "t", "name": "测试公司", "credit_code": "X", "signed_at": "武汉", "domestic_source": "武汉"}

pytestmark = pytest.mark.skipif(not TEST1.is_dir(), reason="需要 box realdata: 缺 test1 样例")


def _pairs():
    out = []
    for name, wh, _ in FILES:
        ship = parse_csv_shipment((TEST1 / name).read_bytes(), allow_unassigned_fba=True, file_name=name)
        out.append(ShipmentPair(ship.shipment_id, ship.warehouse_code, ship, PdfShipment(ship.shipment_id, 0, pages=[])))
    return out


def test_d2_merge_unassigned_tickets(monkeypatch):
    monkeypatch.setattr(
        cp,
        "_catalog_hints",
        lambda sku: {"中文品名": "宠物用品", "单个货值": 10, "申报价来源": "lingxing"},
    )
    data = build_customs_data(_pairs(), [], PROFILE, source="shipment", order_no="T")
    assert data.total_pieces == 145
    assert data.total_gross_kg == 840.9
    assert data.total_net_kg == 811.9
    for wh in ("ONT8", "AVP1", "MDW2", "LAX9", "TOL3"):
        assert wh in data.remarks
    assert "BF26" not in data.remarks


