import pytest
from fba_tool.routing_service import (
    strict_warehouse_from_filename,
    extract_ticket_rank,
    resolve_routing_warehouse,
)


def test_awd_and_new_fba_warehouses():
    # 1. AWD 4-letter warehouses
    assert strict_warehouse_from_filename("第一票-IUSP.csv") == "IUSP"
    assert strict_warehouse_from_filename("第2票_STAR.csv") == "STAR"
    assert strict_warehouse_from_filename("AWD_IUSJ.csv") == "IUSJ"

    # 2. Modern unlisted FBA warehouses
    assert strict_warehouse_from_filename("第1票-ABQ2.csv") == "ABQ2"
    assert strict_warehouse_from_filename("美西_VGT2.csv") == "VGT2"
    assert strict_warehouse_from_filename("PSC2.csv") == "PSC2"
    assert strict_warehouse_from_filename("01_XLX7.csv") == "XLX7"

    # 3. Global overseas warehouses
    assert strict_warehouse_from_filename("第1票-LTN1-英国.csv") == "LTN1"


def test_prefix_and_compact_naming():
    # Number prefix directly connected
    assert strict_warehouse_from_filename("1ONT8.csv") == "ONT8"
    assert strict_warehouse_from_filename("02_LAX9.csv") == "LAX9"
    assert strict_warehouse_from_filename("票1_SMF3.csv") == "SMF3"


def test_blacklist_tokens():
    # Box/CTN/SKU words should not be mistaken for warehouses
    assert strict_warehouse_from_filename("batch_box1.csv") == ""
    assert strict_warehouse_from_filename("50BOX.csv") == ""
    assert strict_warehouse_from_filename("CTN1.csv") == ""
    assert strict_warehouse_from_filename("case1_ONT8.csv") == "ONT8"


def test_extended_ticket_ranks():
    assert extract_ticket_rank("第一票.csv") == 1
    assert extract_ticket_rank("第11票-SMF3.csv") == 11
    assert extract_ticket_rank("第十一票.csv") == 11
    assert extract_ticket_rank("第二十五票.csv") == 25
    assert extract_ticket_rank("1-ONT8.csv") == 1
    assert extract_ticket_rank("02_LAX9.csv") == 2
    assert extract_ticket_rank("票3_GYR3.csv") == 3


def test_routing_mode_resolution():
    wh, src, warn = resolve_routing_warehouse("GYR3", "第1票-ABQ2.csv", is_routing_mode=True)
    assert wh == "ABQ2"
    assert src == "文件名"
    assert warn is not None and "ABQ2" in warn and "GYR3" in warn
