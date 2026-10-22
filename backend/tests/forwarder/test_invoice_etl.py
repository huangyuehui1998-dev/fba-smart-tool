"""invoice_etl 五段流水线单元测试。"""
from __future__ import annotations

import pytest
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


def test_same_model_keeps_one_row_per_sku():
    """型号、单箱量、尺寸都相同的两个 SKU 不能并成 1-32 一行。"""
    rows = []
    for box in range(1, 33):
        for sku, price in (("SKU-A", 10.0), ("TANZI", 49.99)):
            rows.append(
                {
                    "box_id": box,
                    "shipment_id": "FBA13",
                    "sku": sku,
                    "model": "共用型号",
                    "qty": 2,
                    "qty_per_box": 2,
                    "length_cm": 30.0,
                    "width_cm": 20.0,
                    "height_cm": 10.0,
                    "declared_price": price,
                    "fba_box_id": f"FBA13U{box:06d}",
                }
            )
    grouped = _group_by_box_range(pd.DataFrame(rows))
    assert len(grouped) == 2
    assert set(grouped["box_range"]) == {"1-32"}
    assert set(grouped["sku"]) == {"SKU-A", "TANZI"}
    assert set(grouped["model"]) == {"共用型号"}
    by_sku = {row.sku: row.declared_price for row in grouped.itertuples()}
    assert by_sku["SKU-A"] == 10.0
    assert by_sku["TANZI"] == 49.99


def test_qiluo_etl_declared_total_keeps_every_sku():
    from fba_tool.master_db import init_master_db, upsert_product

    init_master_db()
    upsert_product({"sku": "SKU-A", "chinese_name": "品名A", "hs_code": "1111111111", "model_name": "共用型号", "declared_value": 10})
    upsert_product({"sku": "TANZI", "chinese_name": "品名T", "hs_code": "2222222222", "model_name": "共用型号", "declared_value": 49.99})
    box_items = pd.DataFrame(
        [
            {"箱号": 1, "SKU": "SKU-A", "数量": 2},
            {"箱号": 2, "SKU": "SKU-A", "数量": 2},
            {"箱号": 1, "SKU": "TANZI", "数量": 2},
            {"箱号": 2, "SKU": "TANZI", "数量": 2},
        ]
    )
    box_specs = pd.DataFrame(
        [
            {"箱号": 1, "长(cm)": 30, "宽(cm)": 20, "高(cm)": 10, "实重(kg)": 2.0},
            {"箱号": 2, "长(cm)": 30, "宽(cm)": 20, "高(cm)": 10, "实重(kg)": 2.0},
        ]
    )
    ship = CsvShipment(
        shipment_id="FBA13SAME",
        warehouse_code="ONT8",
        box_count=2,
        box_items=box_items,
        box_specs=box_specs,
        box_fba_ids={1: "FBA13SAMEU000001", 2: "FBA13SAMEU000002"},
    )
    items, _warnings = run_invoice_etl(
        forwarder_id="qiluo",
        ship=ship,
        csv_bytes=b"",
        workflow_json=None,
        po_number="",
        catalog=None,
    )
    assert len(items) == 2
    assert {it.values["sku"] for it in items} == {"SKU-A", "TANZI"}
    assert {it.values["box_range"] for it in items} == {"1-2"}
    assert {it.values["model"] for it in items} == {"共用型号"}
    prices = sorted(float(it.values["declared_price"]) for it in items)
    assert prices == [10.0, 49.99]
    assert {type(it.values["declared_price"]) for it in items} == {float}
    assert {type(it.values["qty_per_box"]) for it in items} == {int}
    total = round(sum(float(it.values["total_declared_value_usd"]) for it in items), 2)
    assert total == 239.96


def test_qiluo_declared_price_uses_listing_price_like_send():
    """只有手填售价和发票扩展字段时，申报单价与 SEND 的 resolve_declared_price 相同。"""
    import json

    from fba_tool.master_db import init_master_db, upsert_product
    from fba_tool.product_fields import SOURCE_MANUAL, resolve_declared_price, set_product_fields

    init_master_db()
    prices = {"SKU-PRICE-A": 39.99, "SKU-PRICE-B": 49.99}
    for sku, price in prices.items():
        upsert_product(
            {
                "sku": sku,
                "chinese_name": "品名",
                "hs_code": "9507100090",
                "model_name": "型号",
                "extra_data": json.dumps(
                    {"invoice": {"unit": "个", "purchase_price": 5, "material_en": "cotton", "purpose_en": "pet"}},
                    ensure_ascii=False,
                ),
            }
        )
        set_product_fields(sku, {"listing_price": price, "listing_price_currency": "USD"}, SOURCE_MANUAL)
    box_items = pd.DataFrame(
        [
            {"箱号": 1, "SKU": "SKU-PRICE-A", "数量": 4},
            {"箱号": 2, "SKU": "SKU-PRICE-B", "数量": 4},
        ]
    )
    box_specs = pd.DataFrame(
        [
            {"箱号": 1, "长(cm)": 30, "宽(cm)": 20, "高(cm)": 10, "实重(kg)": 2.0},
            {"箱号": 2, "长(cm)": 30, "宽(cm)": 20, "高(cm)": 10, "实重(kg)": 2.0},
        ]
    )
    ship = CsvShipment(
        shipment_id="FBAPRICE",
        warehouse_code="ONT8",
        box_count=2,
        box_items=box_items,
        box_specs=box_specs,
        box_fba_ids={1: "FBAPRICEU000001", 2: "FBAPRICEU000002"},
    )
    items, warnings = run_invoice_etl(
        forwarder_id="qiluo",
        ship=ship,
        csv_bytes=b"",
        workflow_json=None,
    )
    by_sku = {item.values["sku"]: float(item.values["declared_price"]) for item in items}
    assert by_sku == prices
    assert not any("申报单价为空" in item for item in warnings)
    from fba_tool.master_db import get_product_by_sku

    for sku, price in prices.items():
        resolved, _source = resolve_declared_price(get_product_by_sku(sku))
        assert resolved == price

    empty = CsvShipment(
        shipment_id="FBAPRICEEMPTY",
        warehouse_code="ONT8",
        box_count=3,
        box_items=pd.DataFrame([
            {"箱号": 1, "SKU": "SKU-PRICE-EMPTY", "数量": 1, "FNSKU": "X00TESTEMPTY"},
            {"箱号": 2, "SKU": "SKU-PRICE-EMPTY", "数量": 2, "FNSKU": "X00TESTEMPTY"},
            {"箱号": 3, "SKU": "sku-price-empty", "数量": 1, "FNSKU": "X00TESTEMPTY"},
        ]),
        box_specs=pd.DataFrame([
            {"箱号": 1, "长(cm)": 30, "宽(cm)": 20, "高(cm)": 10, "实重(kg)": 2.0},
            {"箱号": 2, "长(cm)": 30, "宽(cm)": 20, "高(cm)": 18, "实重(kg)": 2.0},
            {"箱号": 3, "长(cm)": 30, "宽(cm)": 20, "高(cm)": 12, "实重(kg)": 2.0},
        ]),
        box_fba_ids={1: "FBAPRICEEMPTYU000001", 2: "FBAPRICEEMPTYU000002", 3: "FBAPRICEEMPTYU000003"},
    )
    upsert_product(
        {
            "sku": "SKU-PRICE-EMPTY",
            "fnsku": "X00TESTEMPTY",
            "extra_data": json.dumps({"invoice": {"unit": "个", "purchase_price": 5}}, ensure_ascii=False),
        }
    )
    from fba_tool.invoice_rules import InvoiceBlocked

    with pytest.raises(InvoiceBlocked) as blocked:
        run_invoice_etl(
            forwarder_id="qiluo",
            ship=empty,
            csv_bytes=b"",
            workflow_json=None,
        )
    reason = blocked.value.blocking[0]
    assert reason["code"] == "price_missing"
    assert reason["skus"] == ["SKU-PRICE-EMPTY / FNSKU X00TESTEMPTY"]
    assert len(reason["skus"]) == 1
    assert reason["message"].casefold().count("sku-price-empty") == 1
    assert "sku sku-" not in reason["message"].casefold()
    assert "FNSKU X00TESTEMPTY" in reason["message"]
    assert "不能导出" in reason["message"]


def test_qiluo_mixed_empty_price_stays_numeric_then_blocks():
    """空价在前时 pandas 3 不能把 49.99 写进 str 列；空申报价与另外五家一样拦截。"""
    import json

    from fba_tool.invoice_rules import InvoiceBlocked
    from fba_tool.master_db import init_master_db, upsert_product
    from fba_tool.product_fields import SOURCE_MANUAL, set_product_fields

    init_master_db()
    upsert_product(
        {
            "sku": "SKU-MIX-PRICE",
            "chinese_name": "有价",
            "hs_code": "9507100090",
            "model_name": "型号",
            "extra_data": json.dumps({"invoice": {"unit": "个"}}, ensure_ascii=False),
        }
    )
    set_product_fields("SKU-MIX-PRICE", {"listing_price": 49.99, "listing_price_currency": "USD"}, SOURCE_MANUAL)
    upsert_product(
        {
            "sku": "SKU-MIX-EMPTY",
            "fnsku": "X00TESTMIX0",
            "chinese_name": "无价",
            "hs_code": "9507100090",
            "model_name": "型号",
            "extra_data": json.dumps({"invoice": {"unit": "个"}}, ensure_ascii=False),
        }
    )

    def ship(order):
        return CsvShipment(
            shipment_id="FBAMIX",
            warehouse_code="ONT8",
            box_count=len(order),
            box_items=pd.DataFrame([{"箱号": i + 1, "SKU": sku, "数量": 4} for i, sku in enumerate(order)]),
            box_specs=pd.DataFrame(
                [{"箱号": i + 1, "长(cm)": 30, "宽(cm)": 20, "高(cm)": 10, "实重(kg)": 2.0} for i in range(len(order))]
            ),
            box_fba_ids={i + 1: f"FBAMIXU{i + 1:06d}" for i in range(len(order))},
        )

    for order in (["SKU-MIX-EMPTY", "SKU-MIX-PRICE"], ["SKU-MIX-PRICE", "SKU-MIX-EMPTY"]):
        with pytest.raises(InvoiceBlocked) as blocked:
            run_invoice_etl(forwarder_id="qiluo", ship=ship(order), csv_bytes=b"", workflow_json=None)
        reason = blocked.value.blocking[0]
        assert reason["code"] == "price_missing"
        assert reason["skus"] == ["SKU-MIX-EMPTY / FNSKU X00TESTMIX0"]
        assert reason["message"].count("SKU-MIX-EMPTY") == 1
        assert "SKU SKU-" not in reason["message"]
        assert "FNSKU X00TESTMIX0" in reason["message"]
        assert "不能导出" in reason["message"]
