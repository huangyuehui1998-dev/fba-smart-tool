"""S8-fix2 N1：按真实领星样本形态（regular_price 每行都等于 listing_price）测 D-12。
真实样本里常规价 = 售价，不能当正常价用：≤ 售价视为“无信息”，回退到近 90 天非促销价；
且判断是否非促销要和上次记下的非促销价比，促销价不得覆盖它（16/16 → 12/12 场景）。"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from test_s5_lingxing_schedule import FAKE_KEY, _factory, env  # noqa: F401  (env 是 fixture)
from test_s8fix1_dec12_e2e import _customs, _promo_warning, _row, _sync
from fba_tool.master_db import get_product_by_sku
from fba_tool.product_fields import _track_nonpromo, normal_price, promo_info, resolve_declared_price

SAMPLE = Path(__file__).parent / "tests" / "fixtures" / "lingxing" / "erp_listing_sample.json"


def _sample_rows():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))["list"]


def test_real_sample_shape_regular_equals_listing():
    rows = _sample_rows()
    assert rows and all(str(r["regular_price"]) == str(r["listing_price"]) for r in rows)


def test_real_sample_rows_never_promo_and_regular_not_used():
    for r in _sample_rows():
        m = {"listing_price": float(r["listing_price"]), "regular_price": float(r["regular_price"])}
        assert normal_price(m) == (None, "")
        assert promo_info(m) is None
        assert resolve_declared_price(m) == (float(r["listing_price"]), "lingxing")


def test_unit_regular_equal_falls_back_to_recent_nonpromo():
    from test_s8_fix import _iso

    m = {"listing_price": 12.0, "regular_price": 12.0, "last_nonpromo_price": 16.0, "last_nonpromo_at": _iso(5)}
    assert resolve_declared_price(m) == (16.0, "lingxing_recent_nonpromo")
    assert promo_info(m)["drop_pct"] == 25.0


def test_unit_track_does_not_overwrite_with_promo_price():
    from test_s8_fix import _iso

    existing = {"regular_price": 16.0, "last_nonpromo_price": 16.0, "last_nonpromo_at": _iso(1)}
    s = {"listing_price": 12.0, "regular_price": 12.0}
    _track_nonpromo(s, existing)
    assert "last_nonpromo_price" not in s
    s2 = {"listing_price": 15.5, "regular_price": 15.5}  # 小于 5% 的调价：仍算非促销，更新
    _track_nonpromo(s2, existing)
    assert s2["last_nonpromo_price"] == 15.5
    s3 = {"listing_price": 16.0, "regular_price": 16.0}  # 没有历史：记下
    _track_nonpromo(s3, {})
    assert s3["last_nonpromo_price"] == 16.0


def test_e2e_real_shape_16_then_12(env):
    _sync([_row("P-RS", 16.0, 16.0)])
    p = get_product_by_sku("P-RS")
    assert p["last_nonpromo_price"] == pytest.approx(16.0)
    assert resolve_declared_price(p) == (pytest.approx(16.0), "lingxing")
    _sync([_row("P-RS", 12.0, 12.0)])
    p = get_product_by_sku("P-RS")
    assert p["listing_price"] == pytest.approx(12.0) and p["regular_price"] == pytest.approx(12.0)
    assert p["last_nonpromo_price"] == pytest.approx(16.0)  # 没被 12 覆盖
    assert resolve_declared_price(p) == (pytest.approx(16.0), "lingxing_recent_nonpromo")
    w = _promo_warning(_customs("P-RS"))
    assert w and "12.00" in w[0]["message"] and "16.00" in w[0]["message"]


def test_e2e_real_sample_row_sync_then_promo(env):
    """用真实样本第一行（15.99/15.99）同步，再模拟降到 11.99/11.99。"""
    base = _sample_rows()[0]
    row = _row(base["msku"], float(base["listing_price"]), float(base["regular_price"]), fnsku=base["fnsku"])
    row.update({k: base[k] for k in ("asin", "item_name", "list_price", "history_price") if k in base})
    _sync([row])
    p = get_product_by_sku(base["msku"])
    assert resolve_declared_price(p) == (pytest.approx(15.99), "lingxing")  # 不用 list_price 38.97
    assert not _promo_warning(_customs(base["msku"]))
    row2 = copy.deepcopy(row)
    row2.update({"price": 11.99, "listing_price": 11.99, "regular_price": 11.99})
    _sync([row2])
    p = get_product_by_sku(base["msku"])
    assert resolve_declared_price(p) == (pytest.approx(15.99), "lingxing_recent_nonpromo")
    assert _promo_warning(_customs(base["msku"]))