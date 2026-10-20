"""S1-fix1：D4 CSV 编码回退。"""
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

pytestmark = pytest.mark.skipif(not TEST1.is_dir(), reason="需要 box realdata: 缺 test1 样例")


def test_d4_gbk_csv_imports():
    raw = (TEST1 / "第一票ONT8.csv").read_bytes().decode("utf-8-sig")
    ship = parse_csv_shipment(raw.encode("gbk"), allow_unassigned_fba=True, file_name="第一票ONT8.csv")
    assert ship.box_count == 29
    assert ship.warehouse_code == "ONT8"


def test_d4_utf8_plain_and_bom():
    raw = (TEST1 / "第一票ONT8.csv").read_bytes().decode("utf-8-sig")
    for b in (raw.encode("utf-8"), b"\xef\xbb\xbf" + raw.encode("utf-8")):
        assert parse_csv_shipment(b, allow_unassigned_fba=True).box_count == 29


def test_d4_undecodable_reports_encoding():
    bad = b"\x81\xff\xfe\x80\x81" * 50
    with pytest.raises(ValueError, match="编码"):
        parse_csv_shipment(bad, allow_unassigned_fba=True)
