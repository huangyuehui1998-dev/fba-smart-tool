"""P1-2 / P1-3 / P1-4：混装标签、未识别箱唛、重复箱唛、失败时的最后一行。"""
from __future__ import annotations

from types import SimpleNamespace

from fba_tool.shipment_cross_check import cross_validate_pair, run_cross_validation
from fba_tool.shipment_parser import CsvShipment, PdfBoxPage


def _csv(box_count: int = 1) -> CsvShipment:
    box_data = {i: {"TEST_A": 10} for i in range(1, box_count + 1)}
    box_fba_ids = {i: f"FBATEST0001U{i:06d}" for i in range(1, box_count + 1)}
    return CsvShipment(
        "FBATEST0001",
        "CLT2",
        box_count,
        box_data=box_data,
        box_fba_ids=box_fba_ids,
    )


def test_mixed_label_on_single_sku_is_one_blocking_error():
    page = PdfBoxPage(0, "FBATEST0001", "FBATEST0001U000001", 1, is_mixed=True)
    errors = cross_validate_pair(_csv(), [page], "CLT2", "FBATEST0001")
    blocking = [e for e in errors if "混装标签异常" in e]
    assert len(blocking) == 1
    assert blocking[0].startswith("❌")


def test_unrecognized_box_labels_are_blocking():
    """SKU、FNSKU、数量都空时，每一页单独 ❌，不再收成一条跳过比对的警告。"""
    csv = _csv(3)
    pages = [
        PdfBoxPage(i, "FBATEST0001", f"FBATEST0001U{i + 1:06d}", i + 1)
        for i in range(3)
    ]
    errors = cross_validate_pair(csv, pages, "CLT2", "FBATEST0001")
    blocking = [e for e in errors if e.startswith("❌") and "都识别不出" in e]
    assert len(blocking) == 3
    assert not any("已跳过逐箱 SKU 比对" in e for e in errors)

    pair = SimpleNamespace(csv=csv, warehouse_code="CLT2", shipment_id="FBATEST0001")
    result = run_cross_validation([pair], {"FBATEST0001": pages})
    assert result.ok is False
    assert sum(1 for line in result.errors if "都识别不出" in line) == 3
    assert result.status_lines[-1].startswith("❌")


def test_duplicate_box_label_lists_page_count():
    pages = [
        PdfBoxPage(i, "FBATEST0001", "FBATEST0001U000001", 1, sku="TEST_A", qty=10)
        for i in range(2)
    ]
    errors = cross_validate_pair(_csv(), pages, "CLT2", "FBATEST0001")
    assert any("U000001 出现 2 页" in e and e.startswith("❌") for e in errors)
    assert any("重复箱唛" in e for e in errors)


def test_missing_pdf_fails_and_last_status_line_is_error():
    csv = _csv()
    pair = SimpleNamespace(csv=csv, warehouse_code="CLT2", shipment_id="FBATEST0001")
    result = run_cross_validation([pair], {"FBATEST0001": []})
    assert result.ok is False
    assert result.status_lines[-1].startswith("❌")
    assert "校验未通过" in result.status_lines[-1]
