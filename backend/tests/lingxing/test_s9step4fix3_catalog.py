"""S9-step4-fix3 / D-19：真实 backend/templates/产品信息表.csv 不随安装包发布，改用 产品信息表_示例.csv（DEMO 值）。
没有真实产品信息表时程序照常运行（运行时只读 SQLite 主库）。"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pytest

from fba_tool import app_paths, product_catalog
from test_s5_lingxing_schedule import env  # noqa: F401  (fixture)

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
EXAMPLE = BACKEND / "templates" / "产品信息表_示例.csv"
SPEC = ROOT / "packaging" / "FBA_Smart_Tool.spec"


def test_example_template_has_header_and_demo_rows_only():
    text = EXAMPLE.read_bytes().decode("utf-8-sig")
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    assert rows[0][2] == "SKU" and "ASIN" in rows[0]
    assert 1 <= len(rows) - 1 <= 5
    for r in rows[1:]:
        assert r[2].startswith("DEMO-") and r[3].startswith("B0DEMO") and r[4].startswith("X0DEMO")
        assert all(("DEMO" in c or "示例" in c or "Demo" in c or re.fullmatch(r"[\d.*]+(cm)?", c)) for c in r), r
    cat = product_catalog.parse_catalog(EXAMPLE)
    assert sorted(cat.records) == ["DEMO-SKU-001", "DEMO-SKU-002"]
    rec = cat.records["DEMO-SKU-001"]
    assert rec.asin == "B0DEMO0001" and rec.fnsku == "X0DEMO0001" and rec.unit_cost == pytest.approx(1.0)


def test_real_catalog_not_in_bundled_templates():
    names = [p.name for p in (BACKEND / "templates").rglob("*") if p.is_file()]
    assert "产品信息表_示例.csv" in names
    assert [n for n in names if app_paths.is_private_template(Path(n))] == []


def _manifest():
    """S9-step5：spec 改用 packaging/release_manifest.py 白名单。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("release_manifest_t", ROOT / "packaging" / "release_manifest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_spec_bundles_example_but_not_real_catalog():
    m = _manifest()
    tpl = set(m.TEMPLATE_WHITELIST)
    assert "产品信息表_示例.csv" in tpl
    assert [r for r in tpl if app_paths.is_private_template(Path(r))] == []
    dests = [d for _, d in m.entries(ROOT)]
    assert "templates/产品信息表_示例.csv" in dests
    assert not any(app_paths.is_private_template(Path(d)) for d in dests)


def test_spec_no_longer_bundles_whole_templates_dir():
    text = SPEC.read_text(encoding="utf-8")
    assert '(str(BACKEND / "templates"), "templates")' not in text
    assert '(str(BACKEND / "config"), "config")' not in text
    assert "*_release_datas(ROOT)," in text
    assert "rglob" not in text


def _only_example(monkeypatch, tmp_path):
    tpl = tmp_path / "tpl"
    tpl.mkdir()
    (tpl / EXAMPLE.name).write_bytes(EXAMPLE.read_bytes())
    monkeypatch.setattr(product_catalog, "templates_dir", lambda: tpl)
    monkeypatch.setattr(product_catalog, "load_catalog_config", lambda: {})
    return tpl


def test_find_catalog_ignores_example(monkeypatch, tmp_path):
    tpl = _only_example(monkeypatch, tmp_path)
    assert product_catalog.find_catalog_path() is None
    assert product_catalog.load_product_catalog() is None
    assert product_catalog.catalog_status_text().startswith("未检测到产品信息表")
    monkeypatch.setattr(product_catalog, "load_catalog_config", lambda: {"source_file": EXAMPLE.name})
    assert product_catalog.find_catalog_path() is None  # 配置指向示例也不读
    (tpl / "产品信息表.csv").write_bytes(EXAMPLE.read_bytes())  # 用户自己放的真实表照常认
    assert product_catalog.find_catalog_path() == tpl / "产品信息表.csv"


def test_startup_without_real_catalog_seeds_nothing_and_app_runs(env, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from fba_tool.catalog_seed import import_catalog_gaps_into_master
    from fba_tool.master_db import get_product_by_sku, list_products
    from main import create_app

    _only_example(monkeypatch, tmp_path)
    before = len(list_products(limit=10_000))
    assert import_catalog_gaps_into_master() == {"scanned": 0, "touched": 0}
    app = create_app()  # 启动时的灌库步骤找不到真实表 → 跳过，不报错
    assert TestClient(app).get("/api/health").status_code == 200
    assert get_product_by_sku("DEMO-SKU-001") is None
    assert len(list_products(limit=10_000)) == before


def test_seed_defaults_skips_private_catalog(monkeypatch, tmp_path):
    bundled = tmp_path / "bundled"
    (bundled / "forwarders").mkdir(parents=True)
    (bundled / "产品信息表.csv").write_text("x", encoding="utf-8")
    (bundled / "产品信息表_示例.csv").write_text("demo", encoding="utf-8")
    (bundled / "forwarders" / "send.xlsx").write_text("demo", encoding="utf-8")
    dest = tmp_path / "ad" / "templates"
    app_paths._merge_dir_missing_files(bundled, dest, skip=app_paths.is_private_template)
    assert sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()) == [
        "forwarders/send.xlsx", "产品信息表_示例.csv"]
    # 旧版升级迁移（不传 skip）照旧搬用户自己的产品信息表
    dest2 = tmp_path / "ad2"
    app_paths._merge_dir_missing_files(bundled, dest2)
    assert (dest2 / "产品信息表.csv").is_file()
