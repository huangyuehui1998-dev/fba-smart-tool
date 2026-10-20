"""S2-6：文件名识别仓库要对照已知仓库表；标出来源；各调用处把文件名传进解析。"""
from __future__ import annotations

from pathlib import Path

import pytest

from fba_tool import shipment_parser as sp
from fba_tool.shipment_parser import _warehouse_from_filename, parse_csv_shipment
from fba_tool.shipment_serialize import csv_shipment_from_dict, csv_shipment_to_dict

TEST1 = Path(__file__).resolve().parents[3] / "test1"


@pytest.mark.parametrize("name", ["JAN5批次.csv", "USA1.csv", "第一票BF26.csv", "MAY2补货.csv"])
def test_filename_tokens_not_in_known_table_rejected(name):
    assert _warehouse_from_filename(name) == ""


@pytest.mark.parametrize("name,wh", [("第一票ONT8.csv", "ONT8"), ("第五票TOL3.csv", "TOL3"), ("FWA4-27箱.csv", "FWA4")])
def test_known_codes_accepted(name, wh):
    assert _warehouse_from_filename(name) == wh


@pytest.mark.skipif(not TEST1.is_dir(), reason="需要 box realdata: 缺 test1")
def test_source_marked_and_serialized():
    raw = (TEST1 / "第一票ONT8.csv").read_bytes()
    ship = parse_csv_shipment(raw, allow_unassigned_fba=True, file_name="第一票ONT8.csv")
    assert ship.warehouse_code == "ONT8" and ship.warehouse_source == "文件名"
    back = csv_shipment_from_dict(csv_shipment_to_dict(ship))
    assert back.warehouse_source == "文件名"
    ship2 = parse_csv_shipment(raw, allow_unassigned_fba=True, file_name="JAN5批次.csv")
    assert ship2.warehouse_code == "UNKN" and ship2.warehouse_source == ""


def _spy(monkeypatch, module):
    seen = {}
    real = sp.parse_csv_shipment

    def fake(data, allow_unassigned_fba=False, file_name=""):
        seen["file_name"] = file_name
        return real(data, allow_unassigned_fba=True, file_name=file_name)

    monkeypatch.setattr(module, "parse_csv_shipment", fake, raising=False)
    monkeypatch.setattr(sp, "parse_csv_shipment", fake)
    return seen


@pytest.mark.skipif(not TEST1.is_dir(), reason="需要 box realdata: 缺 test1")
def test_callers_pass_file_name(monkeypatch):
    raw = (TEST1 / "第二票AVP1.csv").read_bytes()
    from fba_tool import fba_parser, product_catalog, shipment_serialize

    seen = _spy(monkeypatch, shipment_serialize)
    assert shipment_serialize.resolve_csv_shipment(csv_bytes=raw, file_name="第二票AVP1.csv").warehouse_code == "AVP1"
    assert seen["file_name"] == "第二票AVP1.csv"

    seen = _spy(monkeypatch, fba_parser)
    assert fba_parser.parse_amazon_csv(raw, file_name="第二票AVP1.csv")["warehouse_code"] == "AVP1"
    assert seen["file_name"] == "第二票AVP1.csv"

    seen = _spy(monkeypatch, product_catalog)
    assert product_catalog.extract_csv_skus(raw, file_name="第二票AVP1.csv")
    assert seen["file_name"] == "第二票AVP1.csv"


def test_shipment_service_uses_csv_names():
    import inspect

    from fba_tool.shipment_validator import UploadParseResult, ValidationResult
    from services import shipment_service

    assert "csv_names" in UploadParseResult.__dataclass_fields__
    assert "csv_names" in ValidationResult.__dataclass_fields__
    assert "csv_names" in inspect.getsource(shipment_service)
