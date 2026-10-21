"""独立复算的合成用例。不使用第 13 批锚点，也不读 realdata。"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from tests.smoke.reference import LayoutMissing, assemble, chargeable, parse_measure_file, round_up_half_kg


def _book(path: Path, rows: list[list]) -> None:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_round_up_and_chargeable_do_not_use_product_code():
    assert round_up_half_kg("10.01") == Decimal("10.5")
    assert round_up_half_kg("10.50") == Decimal("10.5")
    assert chargeable("10", [10, 10, 10]) == Decimal("10.000")


def test_footer_bill_without_boxes_is_not_added(tmp_path):
    _book(tmp_path / "九方.xlsx", [
        ["外箱号", "运单号", "单箱实重", "长", "宽", "高"],
        ["FBATESTU000001", "WBTEST1", "10.25", 10, 10, 10],
        ["入库计费重", 10.5],
    ])
    parsed = parse_measure_file(tmp_path / "九方.xlsx")
    assert parsed["bills"]["WBTEST1"] == Decimal("10.50")
    assert len(parsed["boxes"]) == 1
    line = chargeable(parsed["boxes"][0]["weight"], parsed["boxes"][0]["dims"])
    assert round_up_half_kg(line) == Decimal("10.5")


def test_present_directory_without_layout_fails(tmp_path):
    (tmp_path / "note.txt").write_text("present", encoding="utf-8")
    with pytest.raises(LayoutMissing):
        assemble(tmp_path)
