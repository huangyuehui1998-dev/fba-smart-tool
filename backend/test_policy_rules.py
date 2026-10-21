"""P1-6 / P1-10 / P1-11 / P1-12 / P1-14 / P1-15：政策边界。"""
from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from fba_tool.fba_compliance import (
    check_box_count_limit,
    enrich_metrics_with_fba_flags,
    evaluate_fba_boxing_compliance,
)
from fba_tool.models import SkuRow
from fba_tool.placement_fee import PlacementFeeEngine
from fba_tool.policy import map_category_name, placement_classes, rule
from fba_tool.sta_template_export import _per_box_metrics_imperial
from main import app

_engine = PlacementFeeEngine()


def _sku(name: str, length: float, width: float, height: float, category: str = "other", unit_kg: float = 1.0) -> SkuRow:
    return SkuRow(
        name,
        10,
        10,
        length,
        width,
        height,
        unit_weight_kg=unit_kg,
        category=category,
    )


def _eval_box(length, width, height, gross, qty=2, category="other", kinds=1, destination="FBA", transport="spd_partnered"):
    if kinds == 1:
        editor = pd.DataFrame([{"箱号": 1, "SKU简称": "TEST_A", "数量": qty}])
        skus = [_sku("TEST_A", length, width, height, category)]
    else:
        editor = pd.DataFrame(
            [
                {"箱号": 1, "SKU简称": "TEST_A", "数量": qty - 1},
                {"箱号": 1, "SKU简称": "TEST_B", "数量": 1},
            ]
        )
        skus = [
            _sku("TEST_A", length, width, height, category),
            _sku("TEST_B", 20, 20, 20, category),
        ]
    metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": gross, "SKU种类": kinds, "件数": qty}])
    return evaluate_fba_boxing_compliance(editor, skus, metrics, transport, destination)


def test_dimension_boundaries():
    assert _eval_box(90, 60, 60, 10)["blocked"] is False
    assert _eval_box(92, 60, 60, 10)["blocked"] is True
    assert _eval_box(64, 64, 40, 10)["blocked"] is True


def test_weight_and_jewelry_boundaries():
    assert _eval_box(40, 30, 20, 22.68)["blocked"] is False
    assert _eval_box(40, 30, 20, 22.69)["blocked"] is True
    jewel = _eval_box(40, 30, 20, 18.2, category="jewelry")
    assert jewel["blocked"] is True
    watch = _eval_box(40, 30, 20, 18.2, category="watch")
    assert watch["blocked"] is True
    unset = _eval_box(40, 30, 20, 18.2, category="")
    assert unset["blocked"] is False
    assert any("未设品类" in line for line in unset["summary_lines"])


def test_unit_count_and_transport():
    passed = _eval_box(40, 30, 20, 10, qty=150)
    assert not any(item.get("level") == "block" and "件" in item["message"] for item in passed["policy_findings"])
    blocked = _eval_box(40, 30, 20, 10, qty=151)
    assert any(item["level"] == "block" and item["source"] == "amazon" for item in blocked["policy_findings"])
    mixed = _eval_box(40, 30, 20, 10, qty=41, kinds=2)
    internal = [item for item in mixed["policy_findings"] if item["source"] == "internal" and item["level"] == "warn"]
    assert len(internal) == 1
    assert internal[0]["source_type"] == "internal"

    assert check_box_count_limit(pd.DataFrame({"箱号": list(range(1, 161))})) is None
    info = check_box_count_limit(pd.DataFrame({"箱号": list(range(1, 202))}))
    assert info["level"] == "info"
    ltl = check_box_count_limit(pd.DataFrame({"箱号": list(range(1, 5002))}), "ltl")
    assert ltl["level"] == "block"
    own = evaluate_fba_boxing_compliance(
        pd.DataFrame({"箱号": list(range(1, 501)), "SKU简称": "TEST_A", "数量": 1}),
        [],
        pd.DataFrame(),
        "spd_own",
    )
    notes = [line for line in own["summary_lines"] if "上限未找到官方出处" in line]
    assert notes == ["自选承运人小包裹箱数上限未找到官方出处，请以 STA 页面为准"]
    assert own["blocked"] is False


def test_fee_tiers_match_policy_and_extra_large_is_zero():
    bounds = {
        "small_standard": [0.5, 1.0],
        "large_standard": [0.75, 1.5, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0],
        "large_oversize": [5.0, 12.0, 28.0, 42.0, 50.0],
    }
    classes = placement_classes()
    for name, highs in bounds.items():
        assert [row["high"] for row in classes[name]] == highs
        for row in classes[name]:
            fees = _engine.lookup_fees(name, row["high"])
            assert fees is not None
            assert fees["1_loc"] == (row["1_loc"][0], row["1_loc"][1])
    unit = _engine.compute_unit(0, 0, 0, 51 * 0.45359237)
    assert unit["size_class"] == "extra_large"
    assert unit["one_location"]["min_usd"] == 0
    assert unit["one_location"]["max_usd"] == 0
    assert "Extra-large：配置费 $0" in unit["fee_note"]
    assert "以 STA 报价为准" in unit["fee_disclaimer"]


def test_oversize_exemption_uses_unit_not_carton():
    sku = SkuRow("TEST_A", 1, 1, 60, 40, 40, unit_weight_kg=1.6)
    editor = pd.DataFrame([{"箱号": 1, "SKU简称": "TEST_A", "数量": 1}])
    metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": 1.6}])
    enriched = enrich_metrics_with_fba_flags(editor, [sku], metrics)
    assert bool(enriched.iloc[0]["FBA超大件豁免"]) is False


def test_mixed_box_uses_carrier_outer_dims():
    sku_map = {
        "TEST_A": SkuRow("TEST_A", 1, 1, 50, 20, 20),
        "TEST_B": SkuRow("TEST_B", 1, 1, 30, 30, 30),
    }
    editor = pd.DataFrame(
        [
            {"箱号": 1, "SKU简称": "TEST_A", "数量": 1},
            {"箱号": 1, "SKU简称": "TEST_B", "数量": 1},
        ]
    )
    metrics = _per_box_metrics_imperial(editor, sku_map, 1)
    assert metrics[1]["length_in"] == round(30 / 2.54, 2)
    assert metrics[1]["width_in"] == round(30 / 2.54, 2)


def test_policy_metadata():
    for key in ("max_units_per_box", "boxes_spd_partnered", "boxes_ltl"):
        item = rule(key)
        assert item["effective_date"] is None
        assert item["verified_at"] == "2026-10-20"
    assert rule("fba_multi_longest_in")["source_type"] == "amazon_official"
    assert "200141510" in rule("fba_multi_longest_in")["source_url"]
    awd = rule("awd_box_side_in")
    assert awd["source_type"] == "pending_verification"
    assert "待核实" in awd["note"]
    assert map_category_name("珠宝") == "jewelry"
    assert map_category_name("Watch") == "watch"
    assert map_category_name("宠物垫") is None
    from fba_tool.lingxing_sync import listing_to_product

    jewelry = listing_to_product({"msku": "TEST_J", "category_name": "首饰"}, "2026-10-20T00:00:00Z")
    assert jewelry["category"] == "jewelry"
    pet = listing_to_product({"msku": "TEST_P", "category_name": "宠物垫"}, "2026-10-20T00:00:00Z")
    assert "category" not in pet


def test_low_multi_box_requires_confirm_then_exports():
    row = {
        "SKU简称": "TEST_A",
        "FNSKU": "X00TESTA1",
        "发货总数": 2,
        "单箱装量": 2,
        "箱长(cm)": 30,
        "箱宽(cm)": 20,
        "箱高(cm)": 15,
        "单个重量(kg)": 0.3,
        "空纸箱重(kg)": 0.2,
        "单箱毛重(kg)": 0.8,
    }
    body = {
        "rows": [row],
        "box_editor": [{"箱号": 1, "来源": "混装", "SKU简称": "TEST_A", "数量": 2}],
    }
    client = TestClient(app)
    blocked = client.post("/api/export/step3/amazon", json={**body, "confirm_weight_warnings": False})
    assert blocked.status_code == 409, blocked.text
    detail = blocked.json()["detail"]
    assert detail["code"] == "BOX_WEIGHT_TOO_LOW"
    assert detail["source_type"] == "internal"
    allowed = client.post("/api/export/step3/amazon", json={**body, "confirm_weight_warnings": True})
    assert allowed.status_code == 200, allowed.text
