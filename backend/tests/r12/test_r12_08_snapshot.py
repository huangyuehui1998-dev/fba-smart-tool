"""R12-08：校验写入申报快照，尺寸按原始英寸全精度保存。"""
from __future__ import annotations

import json
import sqlite3

import pandas as pd

from fba_tool.carton_store import compare_carton, display_declared, snapshot_from_validation
from services.shipment_service import write_validation_snapshot


class _Parsed:
    def __init__(self, ship):
        self.csv_map = {"FBATEST": ship}
        self.csv_names = {"FBATEST": "第13批-CL2.csv"}


class _Ship:
    shipment_id = "FBATEST"
    box_fba_ids = {}
    box_specs = pd.DataFrame([{
        "箱号": 2,
        "FBA箱号": "FBATESTU000002",
        "长(cm)": 45.0,
        "宽(cm)": 45.0,
        "高(cm)": 41.0,
        "实重(kg)": 7.5,
        "declared_in": [17.72, 17.72, 16.14],
        "declared_lb": 16.53,
    }])


class _Ok:
    ok = True


def test_snapshot_keeps_raw_inches_and_displays_rounded():
    ctx = {"parsed": _Parsed(_Ship()), "result": _Ok()}
    snapshot_from_validation(ctx)
    shown = display_declared({"in": [17.72, 17.72, 16.14], "lb": 16.53})
    assert shown["cm"] == [45.01, 45.01, 41.0]
    assert shown["kg"] == 7.498
    from fba_tool.app_paths import master_db_path

    conn = sqlite3.connect(master_db_path())
    try:
        row = conn.execute(
            "SELECT batch, length_cm, declared_to_amazon_json FROM shipment_box_snapshot WHERE fba_box_id=?",
            ("FBATESTU000002",),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == "13"
    assert abs(row[1] - 45.0088) < 0.0001
    assert json.loads(row[2])["in"] == [17.72, 17.72, 16.14]
    assert json.loads(row[2])["lb"] == 16.53


def test_compare_without_snapshot_asks_for_step4():
    report = compare_carton("FBATEST_NONE")
    assert report["message"] == "尚无申报快照，请先完成第 4 步校验"


def test_snapshot_failure_is_returned(monkeypatch):
    def boom(_ctx):
        raise RuntimeError("disk")

    monkeypatch.setattr("fba_tool.carton_store.snapshot_from_validation", boom)
    warning = write_validation_snapshot({"hard_fail": False, "parsed": None, "result": _Ok()})
    assert warning == "申报快照没有写入"
