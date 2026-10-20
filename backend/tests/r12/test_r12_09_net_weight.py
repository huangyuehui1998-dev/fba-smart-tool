"""R12-09：每箱皮重、缺皮重提示、不足 1kg 保留两位。"""
from __future__ import annotations

import sqlite3

from fba_tool.customs_package import compute_net_weight, pop_tare_notes


def test_missing_tare_warns_and_uses_point_two():
    pop_tare_notes()
    notes = []
    net = compute_net_weight(173.50, 21, warnings=notes)
    assert net == 169.30
    assert any("第 1 箱缺皮重，按 0.2kg 计" in item["message"] for item in notes)
    assert "第 21 箱缺皮重，按 0.2kg 计" in pop_tare_notes()


def test_explicit_tares_skip_the_fallback():
    pop_tare_notes()
    assert compute_net_weight(264, 32, [0.3] * 32) == 254.4
    assert pop_tare_notes() == []


def test_sub_kilogram_keeps_two_decimals():
    assert compute_net_weight("0.656", 1, ["0.2"]) == 0.46
    assert compute_net_weight("1.199", 1, ["0.2"]) == 1.00
    assert compute_net_weight("0.7", 1, ["0.2"]) == 0.50


def test_ratio_without_value_uses_default(monkeypatch, tmp_path):
    from fba_tool.master_db import init_master_db
    from fba_tool.warehouse_db import update_rule_profile

    ad = tmp_path / "ad"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    update_rule_profile({"net_weight_mode": "ratio", "net_ratio": None})
    assert compute_net_weight(264, 32) == 250.8


def test_old_minus_per_box_migrates_unless_the_user_chose_it(tmp_path, monkeypatch):
    from fba_tool.db_migrations import run_migrations

    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: tmp_path)
    auto = tmp_path / "auto.db"
    conn = sqlite3.connect(auto)
    conn.execute("CREATE TABLE customs_rule_profile (name TEXT, net_weight_mode TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO customs_rule_profile VALUES ('default', 'minus_per_box', '2020-01-01')")
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    assert run_migrations(conn, str(auto)) == 5
    mode = conn.execute("SELECT net_weight_mode FROM customs_rule_profile").fetchone()[0]
    conn.close()
    assert mode == "tare_from_carton"

    manual = tmp_path / "manual.db"
    conn = sqlite3.connect(manual)
    conn.execute("CREATE TABLE customs_rule_profile (name TEXT, net_weight_mode TEXT, updated_at TEXT)")
    conn.execute("INSERT INTO customs_rule_profile VALUES ('default', 'minus_per_box', '2026-10-01')")
    conn.execute(
        """CREATE TABLE customs_rule_profile_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT, field TEXT, old_value TEXT, new_value TEXT, reason TEXT, created_at TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO customs_rule_profile_history (profile_name, field, old_value, new_value, reason, created_at) VALUES (?,?,?,?,?,?)",
        ("default", "net_weight_mode", "tare_from_carton", "minus_per_box", "user", "2026-10-01"),
    )
    conn.execute("PRAGMA user_version = 4")
    conn.commit()
    run_migrations(conn, str(manual))
    kept = conn.execute("SELECT net_weight_mode FROM customs_rule_profile").fetchone()[0]
    conn.close()
    assert kept == "minus_per_box"
