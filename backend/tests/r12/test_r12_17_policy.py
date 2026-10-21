"""R12-17：200141510 箱规和 GC3Q44PBK8BXQW3Z 配置费。"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pandas as pd

from fba_tool.fba_compliance import evaluate_fba_boxing_compliance, lb_to_kg_exact
from fba_tool.models import SkuRow
from fba_tool.placement_fee import PlacementFeeEngine
from fba_tool.policy import load_policy, placement_classes

_engine = PlacementFeeEngine()
LB = Decimal("0.45359237")


def _cm(inches) -> float:
    return float(Decimal(str(inches)) * Decimal("2.54"))


def _kg(lb) -> float:
    return float(Decimal(str(lb)) * LB)


def _pack(carton, unit, unit_kg, gross, qty=1, category="other"):
    sku = SkuRow(
        "ITEM",
        qty,
        qty,
        _cm(carton[0]),
        _cm(carton[1]),
        _cm(carton[2]),
        unit_weight_kg=unit_kg,
        category=category,
        unit_length_cm=_cm(unit[0]) if unit else 0,
        unit_width_cm=_cm(unit[1]) if unit else 0,
        unit_height_cm=_cm(unit[2]) if unit else 0,
    )
    editor = pd.DataFrame([{"箱号": 1, "SKU简称": "ITEM", "数量": qty}])
    metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": gross}])
    return evaluate_fba_boxing_compliance(editor, [sku], metrics)


def _text(comp) -> str:
    return "\n".join(comp["summary_lines"])


def test_policy_provenance_and_retired_page():
    policy = load_policy()
    for entry in policy["rules"].values():
        assert "source_type" in entry
        assert "source_url" in entry
        assert "verified_at" in entry
        if entry.get("source_type") == "pending_verification":
            assert "待核实" in str(entry.get("note") or "")
    for entry in policy["size_limits_in"].values():
        assert entry["source_type"] == "amazon_official"
        assert entry["weight_source_type"] == "amazon_official_derived"
        assert "GC3Q44PBK8BXQW3Z" in entry["source_url"]
        assert entry["verified_at"] == "2026-10-20"
    fees = policy["placement_fees"]
    assert fees["source_type"] == "amazon_official"
    assert fees["effective_date"] == "2026-01-15"
    assert fees["weight_basis"]["small_standard"] == "unit"
    assert fees["weight_basis"]["large_oversize"] == "max_dim_unit"
    for entry in policy["unverified"].values():
        assert entry["source_type"] == "pending_verification"
        assert "待核实" in entry["note"]
    root = Path(__file__).resolve().parents[2]
    hits = []
    for path in root.rglob("*"):
        if path.suffix not in {".py", ".json", ".md", ".ts", ".tsx"}:
            continue
        if "node_modules" in path.parts or ".git" in path.parts:
            continue
        retired = "G2010" + "81250"
        if retired in path.read_text(encoding="utf-8", errors="ignore"):
            hits.append(str(path))
    assert hits == []


def test_official_fee_table_including_the_twelve_corrections():
    classes = placement_classes()
    expected = {
        "small_standard": [
            (0.5, (0.14, 0.32), None),
            (1.0, (0.16, 0.32), None),
        ],
        "large_standard": [
            (0.75, (0.20, 0.40), None),
            (1.5, (0.24, 0.50), None),
            (3.0, (0.34, 0.60), None),
            (5.0, (0.38, 0.76), None),
            (7.0, (0.40, 0.98), None),
            (10.0, (0.42, 1.20), None),
            (15.0, (0.44, 1.50), None),
            (20.0, (0.55, 1.90), None),
        ],
        "small_oversize": [
            (5.0, (1.10, 1.60), (0.55, 1.10)),
            (12.0, (1.75, 2.40), (0.65, 1.75)),
            (28.0, (2.74, 3.50), (0.81, 2.19)),
            (42.0, (3.95, 4.95), (1.05, 2.83)),
            (50.0, (4.80, 5.95), (1.23, 3.32)),
        ],
        "large_oversize": [
            (5.0, (1.30, 1.80), (0.55, 1.25)),
            (12.0, (2.10, 2.90), (0.65, 1.80)),
            (28.0, (3.40, 4.10), (0.81, 2.30)),
            (42.0, (4.70, 5.60), (1.05, 2.95)),
            (50.0, (5.50, 6.50), (1.23, 3.50)),
        ],
    }
    for name, rows in expected.items():
        stored = classes[name]
        assert [row["high"] for row in stored] == [item[0] for item in rows]
        for stored_row, (high, minimal, partial) in zip(stored, rows):
            assert tuple(stored_row["1_loc"]) == minimal
            assert tuple(stored_row["5_loc"]) == (0, 0)
            if partial is None:
                assert "2_3_loc" not in stored_row
            else:
                assert tuple(stored_row["2_3_loc"]) == partial
            fees = _engine.lookup_fees(name, high)
            assert fees is not None
            assert fees["1_loc"] == minimal
    extra = classes["extra_large"][0]
    assert tuple(extra["1_loc"]) == (0, 0)
    assert tuple(extra["5_loc"]) == (0, 0)


def test_weight_basis_selects_the_official_tier():
    small = _engine.compute_unit(_cm(15), _cm(12), _cm("0.75"), _kg("0.4"))
    assert small["size_class"] == "small_standard"
    assert small["one_location"] == {"min_usd": 0.14, "max_usd": 0.32}
    assert small["split_2_3"] is None

    heavy_dim = _engine.resolve_chargeable_weight(_kg("0.4"), _cm(15), _cm(12), _cm("1.545"), "small_standard")
    assert heavy_dim.dimensional_lb == 2.0
    assert heavy_dim.billing_lb == 0.4
    assert _engine.lookup_fees("small_standard", heavy_dim.billing_lb)["1_loc"] == (0.14, 0.32)
    heavier = _engine.resolve_chargeable_weight(_kg("0.6"), _cm(15), _cm(12), _cm("0.75"), "small_standard")
    assert _engine.lookup_fees("small_standard", heavier.billing_lb)["1_loc"] == (0.16, 0.32)

    large = _engine.compute_unit(_cm(18), _cm(14), _cm(Decimal("556") / Decimal("252")), _kg(1))
    assert large["size_class"] == "large_standard"
    assert large["billing_lb"] == 4.0
    assert large["one_location"] == {"min_usd": 0.38, "max_usd": 0.76}
    assert large["split_2_3"] is None

    bulky_dim = _engine.compute_unit(_cm(40), _cm("10.425"), _cm(2), _kg(4))
    assert bulky_dim["size_class"] == "large_oversize"
    assert bulky_dim["billing_lb"] == 6.0
    assert bulky_dim["one_location"] == {"min_usd": 2.10, "max_usd": 2.90}
    assert bulky_dim["split_2_3"] == {"min_usd": 0.65, "max_usd": 1.80}

    bulky_unit = _engine.compute_unit(_cm(40), _cm("7.81875"), _cm(2), _kg(6))
    assert bulky_unit["billing_lb"] == 6.0
    assert bulky_unit["one_location"]["min_usd"] == 2.10

    bulky_light = _engine.compute_unit(_cm(40), _cm("7.81875"), _cm(2), _kg(4))
    assert bulky_light["billing_lb"] == 4.5
    assert bulky_light["one_location"] == {"min_usd": 1.30, "max_usd": 1.80}

    ten = _engine.compute_unit(_cm(38), _cm(8), _cm(4), _kg(10))
    assert ten["size_class"] == "large_oversize"
    assert ten["one_location"] == {"min_usd": 2.10, "max_usd": 2.90}
    assert ten["split_2_3"] == {"min_usd": 0.65, "max_usd": 1.80}

    extra = _engine.compute_unit(_cm(60), _cm(40), _cm(40), _kg(10))
    assert extra["size_class"] == "extra_large"
    assert extra["one_location"] == {"min_usd": 0.0, "max_usd": 0.0}


def test_multi_box_weight_and_size_boundaries():
    light = _pack((20, 16, 10), (10, 8, 4), 1, 22.6, qty=2)
    assert light["blocked"] is False
    assert "超过内部余量 22.5kg" in _text(light)

    heavy = _pack((20, 16, 10), (10, 8, 4), 1, 22.7, qty=2)
    assert heavy["blocked"] is True
    assert "超过亚马逊 50 lb（22.68kg）上限" in _text(heavy)

    oversize = _pack((36.5, 20, 20), (10, 8, 4), 1, 10, qty=2)
    assert oversize["blocked"] is True
    assert "36×25×25" in _text(oversize)

    exact = _pack((36, 25, 25), (10, 8, 4), 1, 10, qty=2)
    assert exact["blocked"] is False

    exact_lb = _pack((20, 16, 10), (10, 8, 4), 1, float(lb_to_kg_exact("50.00")), qty=2)
    assert exact_lb["blocked"] is False
    assert exact_lb["lift_notices"] == []

    jewel = _pack((20, 16, 10), (8, 6, 2), 0.4, 18.2, qty=1, category="jewelry")
    assert jewel["blocked"] is True


def test_single_oversize_dimension_and_weight_rules():
    passed = _pack((42, 22, 12), (40, 15, 8), 22, 22.5)
    assert passed["blocked"] is False
    assert "箱子明显长于商品" not in _text(passed)

    longer = _pack((48, 22, 12), (40, 15, 8), 22, 22.5)
    assert longer["blocked"] is False
    assert "箱子明显长于商品" in _text(longer)

    two_items = _pack((42, 22, 12), (40, 15, 8), 12, 24, qty=2)
    assert two_items["blocked"] is True

    short_item = _pack((37, 26, 20), (35, 15, 10), 15, 16)
    assert short_item["blocked"] is True

    long_heavy = _pack((42, 22, 12), (40, 15, 8), 22, 25)
    assert long_heavy["blocked"] is True
    assert "50 lb" in _text(long_heavy)
    assert _pack((42, 22, 12), (40, 15, 8), 22, 28)["blocked"] is True

    team = _pack((35, 22, 12), (34, 20, 10), 22, 25)
    assert team["blocked"] is False
    assert team["lift_notices"][0]["label"] == "Team Lift"
    assert _pack((35, 22, 12), (34, 20, 10), 22, 28)["lift_notices"][0]["label"] == "Team Lift"
    assert _pack((35, 22, 12), (34, 20, 10), 22, 30)["blocked"] is True

    rebuilt = _pack((32, 22, 14), (30, 20, 10), 22, 23)
    assert rebuilt["blocked"] is False
    assert rebuilt["lift_notices"][0]["label"] == "Team Lift"

    own_weight = _pack((32, 22, 14), (30, 20, 10), 24, 25)
    assert own_weight["blocked"] is False
    assert own_weight["lift_notices"][0]["label"] == "Team Lift"
    mechanical = _pack((32, 22, 14), (30, 20, 10), 45, 46)
    assert mechanical["blocked"] is False
    assert mechanical["lift_notices"][0]["label"] == "Mechanical Lift"

    two_bulky = _pack((40, 20, 12), (40, 15, 8), 12, 28, qty=2)
    assert two_bulky["blocked"] is True
    assert "50 lb" in _text(two_bulky)
    three_standard = _pack((20, 16, 10), (18, 14, 8), 8.5, 25.5, qty=3)
    assert three_standard["blocked"] is True

    under_65 = _pack((35, 22, 12), (34, 20, 10), 22, 29.48)
    assert under_65["blocked"] is False
    assert under_65["lift_notices"][0]["label"] == "Team Lift"
    over_65 = _pack((35, 22, 12), (34, 20, 10), 22, 29.49)
    assert over_65["blocked"] is True
    assert "65 lb" in _text(over_65)


def test_overlength_and_overweight_overlay_is_pending():
    """(a)+(c) 叠加是本工具读法。只检查界面出现“待核实”，不断言红绿。"""
    comp = _pack((52, 30, 20), (50, 28, 18), 31, 32)
    assert comp["lift_notices"]
    assert comp["lift_notices"][0]["source"] == "pending"
    assert "待核实" in comp["lift_notices"][0]["message"]
