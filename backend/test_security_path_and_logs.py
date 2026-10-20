"""P0-5 / P1-7：task_id 不能逃出历史目录；日志不落密钥和手机号。"""
from __future__ import annotations

import logging

import pytest

from fba_tool.log_redact import redact_text
from fba_tool.session_store import save_history_payload


def test_task_id_cannot_escape_history_dir():
    with pytest.raises(ValueError):
        save_history_payload({"task_id": "../../REPRO_D05", "rows": [{"sku": "TEST_A"}]})


def test_normal_task_id_stays_in_history(monkeypatch, tmp_path):
    history = tmp_path / "history"
    history.mkdir()
    monkeypatch.setattr("fba_tool.session_store.HISTORY_DIR", history)
    monkeypatch.setattr("fba_tool.session_store.SESSIONS_DIR", tmp_path)
    monkeypatch.setattr("fba_tool.session_store.HISTORY_INDEX_PATH", tmp_path / "history_index.json")
    monkeypatch.setattr("fba_tool.session_store._ensure_dirs", lambda: history.mkdir(exist_ok=True))
    task_id = save_history_payload({"task_id": "TESTTASK1", "rows": [{"sku": "TEST_A"}]})
    assert task_id == "TESTTASK1"
    assert (history / "TESTTASK1.json").is_file()
    assert not (tmp_path.parent / "REPRO_D05.json").exists()


def test_logs_redact_secrets_and_phones(caplog):
    from fba_tool.log_redact import install_redacting_logs

    install_redacting_logs()
    log = logging.getLogger("fba_tool.security")
    log.addFilter(logging.getLogger("fba_tool").filters[-1])
    with caplog.at_level(logging.INFO, logger="fba_tool.security"):
        secret = "super-secret" + "-value"
        token = "abcdefghij" + "klmnop"
        phone = "138" + "00138000"
        log.info(f"mcp_key={secret} Bearer {token} phone {phone}")
    text = caplog.text
    assert secret not in text
    assert token not in text
    assert phone not in text
    assert "***" in text
    assert redact_text("api_key=abc12345") == "api_key=***"
