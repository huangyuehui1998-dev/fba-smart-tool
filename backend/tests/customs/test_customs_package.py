"""报关资料数据装配测试。"""
from __future__ import annotations

from fba_tool.customs_package import amount_to_english_words, build_customs_data
from fba_tool.shipment_parser import CsvShipment
from fba_tool.shipment_validator import ShipmentPair
import pandas as pd


def _sample_pair() -> ShipmentPair:
    items = pd.DataFrame(
        [
            {"仓库代码": "VGT2", "箱号": 1, "SKU": "PAD-001", "数量": 100},
            {"仓库代码": "VGT2", "箱号": 2, "SKU": "PAD-001", "数量": 80},
            {"仓库代码": "VGT2", "箱号": 1, "SKU": "PAD-002", "数量": 50},
        ]
    )
    specs = pd.DataFrame(
        [
            {"箱号": 1, "长(cm)": 50, "宽(cm)": 40, "高(cm)": 30, "实重(kg)": 12.5},
            {"箱号": 2, "长(cm)": 50, "宽(cm)": 40, "高(cm)": 30, "实重(kg)": 11.0},
        ]
    )
    ship = CsvShipment(
        shipment_id="FBA19TEST001",
        warehouse_code="VGT2",
        box_count=2,
        box_items=items,
        box_specs=specs,
    )
    from fba_tool.shipment_parser import PdfShipment

    return ShipmentPair("FBA19TEST001", "VGT2", ship, PdfShipment("FBA19TEST001", 0, pages=[]))


def test_merge_by_chinese_name_and_hs(monkeypatch):
    monkeypatch.setattr(
        "fba_tool.customs_package._catalog_hints",
        lambda sku: {"中文品名": "宠物垫", "单个货值": 10, "申报价来源": "lingxing"},
    )
    profile = {
        "id": "test",
        "name": "测试公司",
        "credit_code": "91420113TEST0000",
        "signed_at": "武汉",
        "domestic_source": "武汉",
    }
    step1 = [
        {"SKU": "PAD-001", "单个重量(kg)": 0.5},
        {"SKU": "PAD-002", "单个重量(kg)": 0.4},
    ]
    data = build_customs_data(
        [_sample_pair()],
        step1,
        profile,
        source="shipment",
        order_no="JUS7TEST",
    )
    assert data.order_no == "JUS7TEST"
    assert len(data.lines) >= 1
    assert data.total_qty > 0
    assert "订单编号：JUS7TEST" in data.remarks
    assert data.total_net_kg > 0


def test_amount_to_english_words():
    assert amount_to_english_words(16334.60) == (
        "SIXTEEN THOUSAND THREE HUNDRED THIRTY FOUR US DOLLARS AND SIXTY CENTS ONLY"
    )
    assert amount_to_english_words(16334.00) == "SIXTEEN THOUSAND THREE HUNDRED THIRTY FOUR US DOLLARS ONLY"
    assert amount_to_english_words(0.60) == "ZERO US DOLLARS AND SIXTY CENTS ONLY"
