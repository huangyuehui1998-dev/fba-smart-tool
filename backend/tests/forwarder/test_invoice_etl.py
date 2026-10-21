"""invoice_etl 五段流水线单元测试。"""
from __future__ import annotations

import pandas as pd

from fba_tool.invoice_etl import (
    _consecutive_runs,
    _group_by_box_range,
    _group_detail_rows,
    extract_unpivot,
    group_by_logic,
    run_invoice_etl,
)
from fba_tool.shipment_parser import CsvShipment


def _sample_ship() -> CsvShipment:
    box_items = pd.DataFrame(
        [
            {"箱号": 1, "SKU": "SKU-A", "数量": 2},
            {"箱号": 2, "SKU": "SKU-A", "数量": 2},
            {"箱号": 3, "SKU": "SKU-A", "数量": 2},
            {"箱号": 4, "SKU": "SKU-B", "数量": 1},
        ],
    )
    box_specs = pd.DataFrame(
        [
            {"箱号": 1, "长(cm)": 30, "宽(cm)": 20, "高(cm)": 10, "实重(kg)": 2.0},
            {"箱号": 2, "长(cm)": 30, "宽(cm)": 20, "高(cm)": 10, "实重(kg)": 2.0},
            {"箱号": 3, "长(cm)": 30, "宽(cm)": 20, "高(cm)": 10, "实重(kg)": 2.0},
            {"箱号": 4, "长(cm)": 40, "宽(cm)": 30, "高(cm)": 15, "实重(kg)": 3.0},
        ],
    )
    return CsvShipment(
        shipment_id="FBA123U000001",
        warehouse_code="ONT8",
        box_count=4,
        box_items=box_items,
        box_specs=box_specs,
        box_fba_ids={1: "FBA123U000001", 2: "FBA123U000002", 3: "FBA123U000003", 4: "FBA123U000004"},
    )


def test_consecutive_runs():
    assert _consecutive_runs([1, 2, 3, 5, 6]) == [(1, 3), (5, 6)]


def test_extract_unpivot_row_count():
    df = extract_unpivot(_sample_ship())
    assert len(df) == 4
    assert set(df["sku"].tolist()) == {"SKU-A", "SKU-B"}


def test_detail_row_one_line_per_box():
    df = extract_unpivot(_sample_ship())
    grouped = _group_detail_rows(df)
    assert len(grouped) == 4
    assert grouped.iloc[0]["box_count"] == 1


def test_group_by_box_range_merges_consecutive():
    ship = _sample_ship()
    df = extract_unpivot(ship)
    df["qty_per_box"] = df["qty"]
    df["length_cm"] = 30.0
    df["width_cm"] = 20.0
    df["height_cm"] = 10.0
    df.loc[df["sku"] == "SKU-B", "length_cm"] = 40.0
    df.loc[df["sku"] == "SKU-B", "width_cm"] = 30.0
    df.loc[df["sku"] == "SKU-B", "height_cm"] = 15.0
    grouped = _group_by_box_range(df)
    sku_a = grouped[grouped["sku"] == "SKU-A"]
    sku_b = grouped[grouped["sku"] == "SKU-B"]
    assert len(sku_a) == 1
    assert sku_a.iloc[0]["box_range"] == "1-3"
    assert sku_a.iloc[0]["box_count"] == 3
    assert len(sku_b) == 1
    assert sku_b.iloc[0]["box_range"] == "4"


def test_group_by_box_range_splits_on_qty_change():
    ship = _sample_ship()
    df = extract_unpivot(ship)
    df["qty_per_box"] = df["qty"]
    df.loc[df["box_id"] == 3, "qty_per_box"] = 5
    df["length_cm"] = 30.0
    df["width_cm"] = 20.0
    df["height_cm"] = 10.0
    grouped = _group_by_box_range(df[df["sku"] == "SKU-A"])
    assert len(grouped) == 2
    assert set(grouped["box_range"].tolist()) == {"1-2", "3"}


def test_group_by_logic_detail_row():
    df = extract_unpivot(_sample_ship())
    out = group_by_logic(df, "DETAIL_ROW")
    assert len(out) == 4


def test_group_by_box_range_fba_string_box_id():
    """箱号为 FBA 字符串时，用末尾数字判断连续性。"""
    df = pd.DataFrame(
        [
            {
                "box_id": "FBA19GVFX5SCU000001",
                "shipment_id": "FBA19GVFX5SC",
                "sku": "SKU-A",
                "model": "SKU-A",
                "qty": 2,
                "qty_per_box": 2,
                "length_cm": 30,
                "width_cm": 20,
                "height_cm": 10,
                "fba_box_id": "FBA19GVFX5SCU000001",
            },
            {
                "box_id": "FBA19GVFX5SCU000002",
                "shipment_id": "FBA19GVFX5SC",
                "sku": "SKU-A",
                "model": "SKU-A",
                "qty": 2,
                "qty_per_box": 2,
                "length_cm": 30,
                "width_cm": 20,
                "height_cm": 10,
                "fba_box_id": "FBA19GVFX5SCU000002",
            },
        ]
    )
    grouped = _group_by_box_range(df)
    assert len(grouped) == 1
    assert grouped.iloc[0]["box_range"] == "1-2"


def test_run_invoice_etl_qiluo_merges_box_range():
    from fba_tool.master_db import init_master_db, upsert_product

    init_master_db()
    for sku, cn, hs in [
        ("SKU-A", "品名A", "1111111111"),
        ("SKU-B", "品名B", "2222222222"),
    ]:
        upsert_product({"sku": sku, "chinese_name": cn, "hs_code": hs, "declared_value": 10.0})

    ship = _sample_ship()
    items, warnings = run_invoice_etl(
        forwarder_id="qiluo",
        ship=ship,
        csv_bytes=b"",
        workflow_json=None,
        po_number="PO-001",
        catalog=None,
    )
    assert len(items) == 2
    ranges = sorted(it.values.get("box_range") for it in items)
    assert ranges == ["1-3", "4"]
    assert items[0].values.get("po_number") == "PO-001"
    assert all(it.values.get("chinese_name") for it in items)
    assert all(it.values.get("hs_code") for it in items)
    assert not any("主数据缺少 SKU" in w for w in warnings)
