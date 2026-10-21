"""N4：快照批次取任务或 workflow，文件名里的「第N批」只作兜底。"""
from __future__ import annotations

import sqlite3

import pandas as pd
import pytest


class _Ok:
    ok = True


class _Ship:
    shipment_id = "FBATESTSHIP1"
    box_fba_ids = {1: "FBATESTU000001"}
    box_specs = pd.DataFrame([{
        "箱号": 1,
        "FBA箱号": "FBATESTU000001",
        "长(cm)": 10,
        "宽(cm)": 10,
        "高(cm)": 10,
        "实重(kg)": 5,
    }])


class _Parsed:
    def __init__(self, filename: str):
        self.csv_map = {"FBATESTSHIP1": _Ship()}
        self.csv_names = {"FBATESTSHIP1": filename}
        self.pdf_names = {}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setenv("FBA_APP_DATA_DIR", str(ad))
    monkeypatch.setenv("FBA_DISABLE_SCHEDULER", "1")
    monkeypatch.delenv("FBA_SKIP_MIGRATION", raising=False)
    from fba_tool.master_db import init_master_db

    init_master_db()
    return ad


def _ctx(filename: str, wf=None, task_id: str = ""):
    ctx = {"parsed": _Parsed(filename), "result": _Ok(), "wf": wf or {}}
    if task_id:
        ctx["task_id"] = task_id
        ctx["wf"]["task_id"] = task_id
    return ctx


def _batch(db):
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT batch FROM shipment_box_snapshot").fetchone()[0]
    finally:
        conn.close()


def _compare_box():
    from fba_tool.carton_store import compare_carton, import_measurements

    import_measurements(
        [{
            "kind": "box",
            "fba_id": "WBTEST1",
            "fba_box_id": "FBATESTU000001",
            "weight_kg": 5,
            "length_cm": 10,
            "width_cm": 10,
            "height_cm": 10,
            "chargeable_kg": 5,
        }],
        measured_by="forwarder_jiufang",
        source_file="scan.xlsx",
    )
    report = compare_carton(batch="13")
    assert report["mode"] == "box"
    assert len(report["rows"]) == 1


def test_workflow_batch_wins_over_filename(isolated):
    from fba_tool.carton_store import snapshot_from_validation

    snapshot_from_validation(_ctx("第14批-CL2.csv", {"batch": "13"}))
    assert _batch(isolated / "fba_master.db") == "13"
    _compare_box()


def test_filename_without_batch_uses_saved_task(isolated, monkeypatch):
    from fba_tool.carton_store import snapshot_from_validation

    monkeypatch.setattr(
        "fba_tool.session_store.load_history_payload",
        lambda task_id: {"batch": "13", "task_name": "CL2"} if task_id == "task-13" else None,
    )
    snapshot_from_validation(_ctx("CL2.csv", task_id="task-13"))
    assert _batch(isolated / "fba_master.db") == "13"
    _compare_box()


def test_filename_without_batch_uses_ticket(isolated):
    from fba_tool.carton_store import snapshot_from_validation
    from fba_tool.ticket_import import set_ticket_fields

    set_ticket_fields("FBATESTSHIP1", {"batch": "13"}, "manual")
    snapshot_from_validation(_ctx("CL2.csv"))
    assert _batch(isolated / "fba_master.db") == "13"
    _compare_box()
