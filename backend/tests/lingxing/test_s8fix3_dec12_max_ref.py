"""D-12 方案 A（S8-fix4 N9 改正 S8-fix3）：
- 申报用的正常价：有信息的 regular_price（高于售价）优先；没有时才用近 90 天非促销价（D-12 原文）。
- 较大值 max(有效常规价, 近 90 天非促销价) 只用来判断是否覆盖历史非促销价：本次价 ≥ max×0.95 才更新，否则保留。"""
from __future__ import annotations

import pytest

from test_s5_lingxing_schedule import FAKE_KEY, _factory, env  # noqa: F401  (env 是 fixture)
from test_s8fix1_dec12_e2e import _customs, _promo_warning, _row, _sync
from test_s8_fix import _iso
from fba_tool.master_db import get_product_by_sku
from fba_tool.product_fields import _track_nonpromo, normal_price, promo_info, resolve_declared_price


def test_unit_regular_first_even_if_history_higher():
    """N6 场景按 D-12：常规价 12.5 有信息 → 正常价用 12.5；12 只低 4% → 按 12 报、不提示。"""
    m = {"listing_price": 12.0, "regular_price": 12.5, "last_nonpromo_price": 16.0, "last_nonpromo_at": _iso(3)}
    assert normal_price(m) == (12.5, "lingxing_regular")
    assert resolve_declared_price(m) == (12.0, "lingxing")
    assert promo_info(m) is None


def test_unit_regular_larger_wins():
    m = {"listing_price": 15.0, "regular_price": 20.0, "last_nonpromo_price": 16.0, "last_nonpromo_at": _iso(3)}
    assert resolve_declared_price(m) == (20.0, "lingxing_regular")


def test_unit_no_informative_regular_uses_recent_nonpromo():
    m = {"listing_price": 12.0, "regular_price": 12.0, "last_nonpromo_price": 16.0, "last_nonpromo_at": _iso(3)}
    assert resolve_declared_price(m) == (16.0, "lingxing_recent_nonpromo")


def test_unit_expired_history_ignored_regular_under_5pct_not_promo():
    m = {"listing_price": 12.0, "regular_price": 12.5, "last_nonpromo_price": 16.0, "last_nonpromo_at": _iso(120)}
    assert resolve_declared_price(m) == (12.0, "lingxing")


def test_unit_track_uses_max_ref_to_keep_history():
    existing = {"regular_price": 16.0, "last_nonpromo_price": 16.0, "last_nonpromo_at": _iso(1)}
    s = {"listing_price": 12.0, "regular_price": 12.5}
    _track_nonpromo(s, existing)
    assert "last_nonpromo_price" not in s  # 12 < max(12.5,16)×0.95 → 保留历史 16


def test_e2e_n6_16_then_12_regular_12_5(env):
    _sync([_row("P-N6", 16.0, 16.0)])
    _sync([_row("P-N6", 12.0, 12.5)])
    p = get_product_by_sku("P-N6")
    assert p["listing_price"] == pytest.approx(12.0) and p["regular_price"] == pytest.approx(12.5)
    assert resolve_declared_price(p) == (pytest.approx(12.0), "lingxing")
    assert not _promo_warning(_customs("P-N6"))
    assert p["last_nonpromo_price"] == pytest.approx(16.0)  # 历史值保留


def test_e2e_25_then_20_regular_20_5(env):
    _sync([_row("P-A1", 25.0, 25.0)])
    _sync([_row("P-A1", 20.0, 20.5)])
    p = get_product_by_sku("P-A1")
    assert resolve_declared_price(p) == (pytest.approx(20.0), "lingxing")
    assert not _promo_warning(_customs("P-A1"))
    assert p["last_nonpromo_price"] == pytest.approx(25.0)


def test_e2e_25_then_18_regular_20(env):
    _sync([_row("P-A2", 25.0, 25.0)])
    _sync([_row("P-A2", 18.0, 20.0)])
    p = get_product_by_sku("P-A2")
    assert resolve_declared_price(p) == (pytest.approx(20.0), "lingxing_regular")
    w = _promo_warning(_customs("P-A2"))
    assert w and "18.00" in w[0]["message"] and "20.00" in w[0]["message"]
    assert p["last_nonpromo_price"] == pytest.approx(25.0)