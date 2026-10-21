"""R12-19：点击预算必须来自 Playwright 实跑。无浏览器时跳过 live，有 Chrome 时实跑且不写回文档。"""
from __future__ import annotations

import importlib.util
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load_click_count():
    path = ROOT / "scripts" / "e2e" / "click_count.py"
    spec = importlib.util.spec_from_file_location("click_count_r12_19", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_step_table_budget_is_half():
    module = _load_click_count()
    baseline = module.tally(module.BASELINE_STEPS)
    current = module.tally(module.CURRENT_STEPS)
    assert baseline == {"clicks": 18, "manual_cell_edits": 8}
    assert current == {"clicks": 9, "manual_cell_edits": 2}
    assert current["clicks"] <= baseline["clicks"] * 0.5
    assert current["manual_cell_edits"] <= baseline["manual_cell_edits"] * 0.5


def test_live_click_count_skips_without_browser(monkeypatch):
    module = _load_click_count()
    monkeypatch.setenv("FBA_E2E_SKIP", "1")
    assert module.browser_available() is False


def test_live_playwright_matches_click_budget(monkeypatch):
    module = _load_click_count()
    if not module.browser_available():
        pytest.skip("无 Playwright/Chrome，跳过 live 点击计数")
    monkeypatch.delenv("FBA_E2E_URL", raising=False)
    before_baseline = module.BASELINE_PATH.read_bytes()
    before_events = module.EVENTS_PATH.read_bytes()
    payload = module.measure(write=False)
    assert module.BASELINE_PATH.read_bytes() == before_baseline
    assert module.EVENTS_PATH.read_bytes() == before_events
    assert payload["playwright_live"] is True
    assert "已核实" in payload["verification"]
    assert payload["baseline"] == {"clicks": 18, "manual_cell_edits": 8}
    assert payload["current"] == {"clicks": 9, "manual_cell_edits": 2}
    assert payload["current"]["clicks"] <= payload["baseline"]["clicks"] * 0.5
    assert payload["current"]["manual_cell_edits"] <= payload["baseline"]["manual_cell_edits"] * 0.5
    assert len(payload["baseline_events"]) == 26
    assert len(payload["current_events"]) == 11
    assert module.tally(payload["baseline_events"]) == payload["baseline"]
    assert module.tally(payload["current_events"]) == payload["current"]


def test_e2e_url_rejects_page_without_step_controls(monkeypatch):
    module = _load_click_count()
    if not module.browser_available():
        pytest.skip("无 Playwright/Chrome，跳过 live 点击计数")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"<!DOCTYPE html><html><body><p>no controls</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    before_baseline = module.BASELINE_PATH.read_bytes()
    before_events = module.EVENTS_PATH.read_bytes()
    monkeypatch.setenv("FBA_E2E_URL", f"http://127.0.0.1:{server.server_address[1]}/")
    try:
        with pytest.raises(module.ClickPathError):
            module.measure(write=True)
        assert module.BASELINE_PATH.read_bytes() == before_baseline
        assert module.EVENTS_PATH.read_bytes() == before_events
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
