"""PR-4 技术债：单位、历史索引、净重无关的排箱提示、仓区、开发库路径。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fba_tool.boxing import calculate_boxes, remainder_split_count
from fba_tool.models import SkuRow
from fba_tool.placement_fee import PlacementFeeEngine, warehouse_region
from fba_tool.sta_template_export import _kg_to_lb
from fba_tool.units import KG_TO_LB, LB_IN_KG


def test_sta_and_placement_share_lb_conversion():
    kg = 12.5
    exact = PlacementFeeEngine.kg_to_lb(kg)
    assert exact == pytest.approx(float(kg / float(LB_IN_KG)))
    assert _kg_to_lb(kg) == pytest.approx(round(exact, 2))
    assert KG_TO_LB == pytest.approx(exact / kg)


def test_no_legacy_lb_factor_literal():
    root = Path(__file__).resolve().parents[2]
    bad = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".py", ".json", ".txt", ".md"}:
            continue
        if "legacy_streamlit" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "2." + "2046" in text:
            bad.append(path.relative_to(root).as_posix())
    assert bad == []


def test_history_index_keeps_1001_and_stays_json_if_replace_fails(monkeypatch, tmp_path):
    from fba_tool import session_store

    history = tmp_path / "sessions" / "history"
    history.mkdir(parents=True)
    index = tmp_path / "sessions" / "history_index.json"
    monkeypatch.setattr(session_store, "HISTORY_DIR", history)
    monkeypatch.setattr(session_store, "HISTORY_INDEX_PATH", index)
    monkeypatch.setattr(session_store, "SESSIONS_DIR", tmp_path / "sessions")

    for i in range(1001):
        session_store.save_history_payload({"task_id": f"T{i:04d}", "task_name": f"task-{i}", "input_rows": [{"SKU简称": "TEST_A"}]})
    listed = session_store.list_history_tasks()
    assert len(listed) == 1001
    page = session_store.list_history_tasks(offset=1000, limit=50)
    assert len(page) == 1

    before = index.read_text(encoding="utf-8")
    json.loads(before)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(session_store.os, "replace", _boom)
    with pytest.raises(RuntimeError):
        session_store.save_history_payload({"task_id": "T-FAIL", "task_name": "fail", "input_rows": [{"SKU简称": "TEST_A"}]})
    json.loads(index.read_text(encoding="utf-8"))
    assert len(session_store.list_history_tasks()) == 1001


def test_remainder_of_three_skus_stays_together():
    rows = [
        SkuRow(sku=name, total_qty=10, carton_qty=100, length_cm=20, width_cm=20, height_cm=20, unit_weight_kg=0.1, carton_tare_kg=0.2)
        for name in ("TEST_A", "TEST_B", "TEST_C")
    ]
    plans, _tail, warnings = calculate_boxes(rows, max_weight_kg=22.5)
    assert warnings == []
    assert remainder_split_count(plans) == 0


def test_calculate_boxes_warns_when_one_unit_exceeds_limit():
    rows = [
        SkuRow(sku="TEST_HEAVY", total_qty=1, carton_qty=1, length_cm=40, width_cm=30, height_cm=20, unit_weight_kg=25, carton_tare_kg=0.2)
    ]
    _plans, _tail, warnings = calculate_boxes(rows, max_weight_kg=22.5)
    assert warnings and "超过上限" in warnings[0]


def test_batch_warehouse_codes_have_regions():
    codes = ["CLT2", "LAS1", "LAX9", "TEB9", "SBD1", "ONT8", "MDW2"]
    assert all(warehouse_region(code) != "其他" for code in codes)


def test_dev_master_db_lives_in_app_data(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    monkeypatch.setenv("FBA_APP_DATA_DIR", str(ad))
    from fba_tool import app_paths
    from fba_tool import master_db

    monkeypatch.setattr(app_paths, "app_data_dir", lambda: ad)
    monkeypatch.setattr(master_db, "_master_db_file", lambda: ad / "fba_master.db")
    assert master_db.master_db_path() == ad / "fba_master.db"
    assert master_db.master_db_path().name == "fba_master.db"


def test_spa_catchall_serves_seven_paths(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!DOCTYPE html><html><body><div id=\"root\"></div></body></html>", encoding="utf-8")
    monkeypatch.setenv("FBA_DISABLE_SCHEDULER", "1")
    import main

    monkeypatch.setattr(main, "_frontend_dist_dir", lambda: str(dist))
    app = main.create_app()
    client = TestClient(app)
    paths = ["/", "/master-data", "/pdf-labels", "/step/1", "/step/2", "/step/3", "/step/4"]
    assert len(paths) == 7
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, path
        assert 'id="root"' in response.text


def test_invoice_dimension_text_keeps_two_decimals():
    from fba_tool.invoice_export import _fmt_dim

    assert _fmt_dim(10) == "10.00"
    assert _fmt_dim(10.5) == "10.50"


def test_root_docs_are_not_duplicated():
    root = Path(__file__).resolve().parents[3]
    names = [p.name for p in root.iterdir() if p.suffix.lower() in {".md", ".txt"} and p.is_file()]
    assert len(names) <= 3
    assert (root / "docs" / "使用说明.md").is_file()
    assert (root / "docs" / "架构说明.md").is_file()
