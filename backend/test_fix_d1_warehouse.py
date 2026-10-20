"""S1-fix1：D1 仓库识别。"""
from __future__ import annotations

from pathlib import Path

import pytest

from fba_tool import customs_package as cp
from fba_tool.customs_package import build_customs_data
from fba_tool.shipment_parser import PdfShipment, parse_csv_shipment
from fba_tool.shipment_validator import ShipmentPair

TEST1 = Path(__file__).resolve().parent.parent / "test1"
FILES = [
    ("第一票ONT8.csv", "ONT8", 29),
    ("第二票AVP1.csv", "AVP1", 32),
    ("第三票MDW2.csv", "MDW2", 34),
    ("第四票LAX9.csv", "LAX9", 25),
    ("第五票TOL3.csv", "TOL3", 25),
]
PROFILE = {"id": "t", "name": "测试公司", "credit_code": "X", "signed_at": "武汉", "domestic_source": "武汉"}

pytestmark = pytest.mark.skipif(not TEST1.is_dir(), reason="缺 test1 样例")


@pytest.mark.parametrize("name,wh,boxes", FILES)
def test_d1_warehouse_from_filename(name, wh, boxes):
    ship = parse_csv_shipment((TEST1 / name).read_bytes(), allow_unassigned_fba=True, file_name=name)
    assert ship.warehouse_code == wh
    assert ship.shipment_id == "待分配"


@pytest.mark.parametrize("name,wh,boxes", FILES)
def test_d1_never_takes_code_from_workflow_uuid(name, wh, boxes):
    ship = parse_csv_shipment((TEST1 / name).read_bytes(), allow_unassigned_fba=True)
    assert ship.warehouse_code != "BF26"
    assert ship.warehouse_code in ("UNKN", "")


