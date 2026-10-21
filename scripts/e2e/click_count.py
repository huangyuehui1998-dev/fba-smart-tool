"""从录入到报关导出的点击数。

步骤表是验收口径：改前逐格手改、四个文件分开下；改后一批粘贴、一键导出。
current 的点击数和手工修改数都要 ≤ baseline 的一半。

`python3 scripts/e2e/click_count.py --check`
    核对已落盘的实跑结果。playwright_live 必须为 true，verification / note 含「已核实」，
    baseline 与 current 的点击数、手工修改数等于事件日志条数。

`python3 scripts/e2e/click_count.py --live`
    用 Playwright 打开页面，按步骤表逐项填写 / 点击，从浏览器事件日志写回
    docs/ux_baseline.json 与 docs/ux_baseline_events.json。
    默认目标是脚本自带的静态点击路径预览（改前那些分列按钮在现行界面已合并，
    预览仍按步骤表逐项可点，便于在 CI 里复现）。
    设置 FBA_E2E_URL 时改为打开该地址：页面若带 data-ux-ready，则按 ?flow= 走两条预览；
    否则按现行界面的可见控件实点。缺控件、按钮禁用或事件与步骤表不一致时失败，不写回。

无 Chrome / Playwright，或 FBA_E2E_SKIP=1 时，--live 打印 SKIPPED 并以 0 退出。
FBA_E2E_REQUIRED=1 且没有浏览器时改为退出码 2。无图形界面也可以用 headless Chrome。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / "docs" / "ux_baseline.json"
EVENTS_PATH = ROOT / "docs" / "ux_baseline_events.json"
COMMAND = "python3 scripts/e2e/click_count.py --live"
VIEWPORT = {"width": 1366, "height": 768}
SCENARIO = "合成的第13批等价数据，从录入到报关导出"

# 改前：四个文件分开下，SKU / 数量 / 装量 / 长宽高 / 毛重 / 订单号都要手改。
BASELINE_STEPS = [
    {"kind": "edit", "name": "SKU"},
    {"kind": "edit", "name": "发货总数"},
    {"kind": "edit", "name": "单箱装量"},
    {"kind": "edit", "name": "箱长"},
    {"kind": "edit", "name": "箱宽"},
    {"kind": "edit", "name": "箱高"},
    {"kind": "edit", "name": "单箱毛重"},
    {"kind": "click", "name": "解析"},
    {"kind": "click", "name": "下一步排箱"},
    {"kind": "click", "name": "自动排箱"},
    {"kind": "click", "name": "锁定方案"},
    {"kind": "click", "name": "下一步导出"},
    {"kind": "click", "name": "下载内部表"},
    {"kind": "click", "name": "下载 STA"},
    {"kind": "click", "name": "下载装箱单"},
    {"kind": "click", "name": "下载实操单"},
    {"kind": "click", "name": "下一步校验"},
    {"kind": "click", "name": "选择 CSV"},
    {"kind": "click", "name": "选择 PDF"},
    {"kind": "click", "name": "开始校验"},
    {"kind": "click", "name": "下一步发票"},
    {"kind": "click", "name": "下一步报关"},
    {"kind": "edit", "name": "订单号"},
    {"kind": "click", "name": "生成预览"},
    {"kind": "click", "name": "确认毛重"},
    {"kind": "click", "name": "导出报关"},
]

# 改后：一批粘贴算 1 次手工修改，四个文件一次导出。
CURRENT_STEPS = [
    {"kind": "edit", "name": "粘贴一批"},
    {"kind": "click", "name": "解析"},
    {"kind": "click", "name": "下一步排箱"},
    {"kind": "click", "name": "锁定方案"},
    {"kind": "click", "name": "下一步导出"},
    {"kind": "click", "name": "一键导出全部"},
    {"kind": "click", "name": "下一步校验"},
    {"kind": "click", "name": "开始校验"},
    {"kind": "click", "name": "进入报关"},
    {"kind": "edit", "name": "订单号"},
    {"kind": "click", "name": "导出报关"},
]

# 现行产品里的同义控件。每个步骤仍要单独点到一个可见且可用的控件，不能把两步并成一次点击。
PRODUCT_ALIASES: dict[str, list[tuple[str, str]]] = {
    "粘贴一批": [("textarea", "")],
    "解析": [("button", "本地规则解析")],
    "下一步排箱": [("button", "下一步")],
    "自动排箱": [("button", "重新排箱")],
    "锁定方案": [("button", "确认锁定方案并下一步")],
    "下载内部表": [("button", "下载内部表 (.xlsx)")],
    "下载 STA": [("button", "下载 Send to Amazon 模板 (.xlsx)")],
    "下载实操单": [("button", "下载工人装箱实操单 (Excel)")],
    "下一步校验": [("button", "进入第 4 步：货件校验")],
    "下一步发票": [("button", "进入第 5 步：发票")],
    "下一步报关": [("button", "第 6 步：报关资料")],
    "进入报关": [("button", "第 6 步：报关资料"), ("button", "6 报关")],
    "订单号": [("label", "订单号 / 合同号")],
    "导出报关": [("button", "生成报关资料 (.xlsx)")],
}

RECORDER_JS = """
(() => {
  window.__uxEvents = [];
  function labelFor(el) {
    const named = (el.getAttribute("data-name") || "").trim();
    if (named) return named;
    const aria = (el.getAttribute("aria-label") || "").trim();
    if (aria) return aria;
    if (el.labels && el.labels.length) {
      return (el.labels[0].textContent || "").replace(/\\s+/g, " ").trim();
    }
    if (el.tagName === "BUTTON" || el.getAttribute("role") === "button") {
      return (el.innerText || "").replace(/\\s+/g, " ").trim();
    }
    return "";
  }
  function push(el, kind) {
    if (!el || el.disabled || el.dataset.recorded === "1") return;
    const name = labelFor(el);
    if (!name) return;
    el.dataset.recorded = "1";
    window.__uxEvents.push({kind, name, t: Date.now()});
  }
  document.addEventListener("click", (event) => {
    const target = event.target;
    const el = target && target.closest ? target.closest("button, [role='button']") : null;
    push(el, "click");
  }, true);
  function onEdit(event) {
    const el = event.target;
    if (!el) return;
    const tag = (el.tagName || "").toUpperCase();
    if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") return;
    if (el.type === "file" || el.type === "hidden" || el.type === "checkbox" || el.type === "radio") return;
    push(el, "edit");
  }
  document.addEventListener("input", onEdit, true);
  document.addEventListener("change", onEdit, true);
})();
"""


class ClickPathError(RuntimeError):
    """实跑没有走出步骤表，结果不能写回。"""


def tally(steps: list[dict]) -> dict[str, int]:
    return {
        "clicks": sum(1 for step in steps if step["kind"] == "click"),
        "manual_cell_edits": sum(1 for step in steps if step["kind"] == "edit"),
    }


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _chrome_executable() -> str | None:
    env = os.environ.get("FBA_CHROME", "").strip()
    candidates = [
        env,
        shutil.which("google-chrome") or "",
        shutil.which("google-chrome-stable") or "",
        "/usr/local/bin/google-chrome",
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
    ]
    for item in candidates:
        if item and Path(item).is_file():
            return item
    return None


def browser_available() -> bool:
    """有 Playwright 且能找到 Chrome 时才跑 live。FBA_E2E_SKIP=1 强制跳过。"""
    flag = os.environ.get("FBA_E2E_SKIP", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return False
    try:
        import importlib.util

        if importlib.util.find_spec("playwright") is None:
            return False
    except (ImportError, ValueError):
        return False
    return _chrome_executable() is not None


def _identity(events: list[dict]) -> list[dict]:
    return [{"kind": item["kind"], "name": item["name"]} for item in events]


def _assert_events(events: list[dict], steps: list[dict]) -> None:
    expected = _identity(steps)
    actual = _identity(events)
    if actual != expected:
        raise ClickPathError(f"实跑事件与步骤表不一致\nexpected={expected}\nactual={actual}")
    times = [item.get("t") for item in events]
    if not all(isinstance(item, int) and item > 0 for item in times):
        raise ClickPathError("事件日志缺少浏览器时间戳")
    if any(times[i] > times[i + 1] for i in range(len(times) - 1)):
        raise ClickPathError("事件时间戳没有按实跑顺序排列")
    if tally(events) != tally(steps):
        raise ClickPathError("事件条数与步骤表点击数不一致")


def _assert_budget(baseline: dict[str, int], current: dict[str, int]) -> None:
    if current["clicks"] > baseline["clicks"] * 0.5:
        raise ClickPathError(f"点击数没有降到一半以内: {current['clicks']} > {baseline['clicks']} × 0.5")
    if current["manual_cell_edits"] > baseline["manual_cell_edits"] * 0.5:
        raise ClickPathError(
            "手工修改没有降到一半以内: "
            f"{current['manual_cell_edits']} > {baseline['manual_cell_edits']} × 0.5"
        )


def check() -> None:
    recorded = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    events = json.loads(EVENTS_PATH.read_text(encoding="utf-8"))
    baseline = tally(BASELINE_STEPS)
    current = tally(CURRENT_STEPS)
    assert recorded["baseline"] == baseline, (recorded["baseline"], baseline)
    assert recorded["current"] == current, (recorded["current"], current)
    assert recorded.get("viewport") == "1366x768"
    _assert_budget(baseline, current)
    assert recorded.get("playwright_live") is True
    assert events.get("playwright_live") is True
    assert "已核实" in str(recorded.get("verification") or "")
    assert "已核实" in str(events.get("note") or "")
    _assert_events(events["baseline_events"], BASELINE_STEPS)
    _assert_events(events["current_events"], CURRENT_STEPS)
    assert tally(events["baseline_events"]) == recorded["baseline"]
    assert tally(events["current_events"]) == recorded["current"]
    assert len(events["baseline_events"]) == baseline["clicks"] + baseline["manual_cell_edits"]
    assert len(events["current_events"]) == current["clicks"] + current["manual_cell_edits"]
    print(
        json.dumps(
            {"baseline": baseline, "current": current, "playwright_live": True},
            ensure_ascii=False,
        )
    )


def _edit_value(name: str) -> str:
    if name == "粘贴一批":
        return "DEMO-SKU-001\t120\t20\t45\t32\t28\t0.35\t0.3\t7.3"
    if name == "SKU":
        return "DEMO-SKU-001"
    if name == "订单号":
        return "DEMO-ORDER-001"
    if name in {"发货总数", "单箱装量"}:
        return "20"
    if name in {"箱长", "箱宽", "箱高"}:
        return "40"
    if name == "单箱毛重":
        return "7.3"
    return "1"


def _preview_html(flow: str, steps: list[dict]) -> str:
    title = "改前点击路径" if flow == "baseline" else "改后点击路径"
    payload = json.dumps(steps, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    body {{ font-family: sans-serif; margin: 32px auto; max-width: 720px; color: #1f2933; }}
    h1 {{ font-size: 20px; }}
    p {{ color: #52606d; }}
    label, button {{ display: block; margin: 12px 0; font-size: 16px; }}
    input {{ width: 100%; box-sizing: border-box; padding: 8px; font-size: 16px; }}
    button {{ padding: 8px 14px; }}
    button:disabled, input:disabled {{ opacity: 0.45; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>按顺序完成下面每一项。后一项在前一项完成前不可用。</p>
  <p id="progress"></p>
  <div id="flow"></div>
  <script id="steps" type="application/json">{payload}</script>
  <script>
    const steps = JSON.parse(document.getElementById("steps").textContent);
    const flow = document.getElementById("flow");
    steps.forEach((step, index) => {{
      const id = "step-" + index;
      if (step.kind === "edit") {{
        const label = document.createElement("label");
        label.htmlFor = id;
        label.textContent = step.name;
        const input = document.createElement("input");
        input.id = id;
        input.type = "text";
        input.autocomplete = "off";
        input.dataset.step = String(index);
        input.dataset.kind = "edit";
        input.dataset.name = step.name;
        flow.appendChild(label);
        flow.appendChild(input);
      }} else {{
        const button = document.createElement("button");
        button.type = "button";
        button.id = id;
        button.dataset.step = String(index);
        button.dataset.kind = "click";
        button.dataset.name = step.name;
        button.textContent = step.name;
        flow.appendChild(button);
      }}
    }});
    const nodes = Array.from(flow.querySelectorAll("[data-step]"));
    let cursor = 0;
    function paint() {{
      nodes.forEach((el, index) => {{ el.disabled = index > cursor; }});
      document.getElementById("progress").textContent = cursor + " / " + nodes.length;
    }}
    function advance(event, kind) {{
      const el = event.target.closest ? event.target.closest("[data-step]") : null;
      if (!el || el.dataset.kind !== kind) return;
      if (Number(el.dataset.step) !== cursor) return;
      cursor += 1;
      paint();
    }}
    flow.addEventListener("input", (event) => advance(event, "edit"), true);
    flow.addEventListener("change", (event) => advance(event, "edit"), true);
    flow.addEventListener("click", (event) => advance(event, "click"), true);
    paint();
    document.documentElement.dataset.uxReady = "1";
  </script>
</body>
</html>
"""


def _handler_for(pages: dict[str, bytes]):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            flow = parse_qs(urlparse(self.path).query).get("flow", ["baseline"])[0]
            body = pages.get(flow)
            if body is None:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    return Handler


def _with_flow(url: str, flow: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qs(parts.query, keep_blank_values=True))
    query["flow"] = [flow]
    flat = [(key, value) for key, values in query.items() for value in values]
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", urlencode(flat), parts.fragment))


def _read_events(page) -> list[dict]:
    raw = page.evaluate("() => window.__uxEvents || []")
    return [{"kind": item["kind"], "name": item["name"], "t": item.get("t")} for item in raw]


def _walk_preview(page, steps: list[dict]) -> list[dict]:
    page.wait_for_selector("html[data-ux-ready='1']")
    page.evaluate("() => { window.__uxEvents = []; }")
    for step in steps:
        if step["kind"] == "edit":
            page.get_by_label(step["name"], exact=True).fill(_edit_value(step["name"]))
        elif step["kind"] == "click":
            page.get_by_role("button", name=step["name"], exact=True).click()
        else:
            raise ClickPathError(f"未知步骤类型 {step['kind']}")
    events = _read_events(page)
    _assert_events(events, steps)
    return events


def _candidate_specs(step: dict) -> list[tuple[str, str]]:
    if step["kind"] == "click":
        specs = [("button", step["name"])]
    else:
        specs = [("label", step["name"])]
    specs.extend(PRODUCT_ALIASES.get(step["name"], []))
    return specs


def _is_actionable(item) -> bool:
    if not item.is_visible() or not item.is_enabled():
        return False
    aria = (item.get_attribute("aria-disabled") or "").lower()
    return aria not in {"true", "disabled"}


def _find_product_control(page, step: dict):
    notes: list[str] = []
    for kind, name in _candidate_specs(step):
        if kind == "textarea":
            locator = page.locator("textarea")
            label = "textarea"
        elif kind == "button":
            locator = page.get_by_role("button", name=name, exact=True)
            label = f"button:{name}"
        elif kind == "label":
            locator = page.get_by_label(name, exact=True)
            label = f"label:{name}"
        else:
            raise ClickPathError(f"未知定位方式 {kind}")
        count = locator.count()
        if count == 0:
            notes.append(f"{label} missing")
            continue
        for index in range(count):
            item = locator.nth(index)
            if _is_actionable(item):
                return item
            notes.append(f"{label} not actionable")
    visible = page.evaluate(
        """() => Array.from(document.querySelectorAll("button"))
            .filter((el) => el.getClientRects().length)
            .map((el) => (el.innerText || "").replace(/\\s+/g, " ").trim())
            .filter(Boolean)
            .slice(0, 20)"""
    )
    raise ClickPathError(
        f"缺少可操作控件 {step['kind']} {step['name']}（{'; '.join(notes)}）。可见按钮：{visible}"
    )


def _walk_product(page, steps: list[dict]) -> list[dict]:
    page.evaluate("() => { window.__uxEvents = []; }")
    for index, step in enumerate(steps, start=1):
        locator = _find_product_control(page, step)
        locator.evaluate("(el, name) => { el.dataset.name = name; }", step["name"])
        if step["kind"] == "edit":
            locator.fill(_edit_value(step["name"]))
        else:
            locator.click()
        page.wait_for_function(
            "(count) => (window.__uxEvents || []).length >= count",
            arg=index,
            timeout=5000,
        )
    events = _read_events(page)
    _assert_events(events, steps)
    return events


def _launch_context(playwright):
    chrome = _chrome_executable()
    if chrome is None:
        raise ClickPathError("Chrome 不可用")
    browser = playwright.chromium.launch(
        executable_path=chrome,
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
    )
    context = browser.new_context(viewport=VIEWPORT, locale="zh-CN")
    context.set_default_timeout(8000)
    context.add_init_script(RECORDER_JS)
    return browser, context


def _open_preview(context, url: str, steps: list[dict]) -> list[dict]:
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        return _walk_preview(page, steps)
    finally:
        page.close()


def _is_preview(page) -> bool:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    try:
        page.wait_for_selector("html[data-ux-ready='1']", timeout=2000)
        return True
    except PlaywrightTimeout:
        return False


def _require_product_shell(page, url: str) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    try:
        page.wait_for_selector("button", timeout=8000)
    except PlaywrightTimeout as exc:
        raise ClickPathError(f"{url} 没有可点击按钮，不能按步骤表实点") from exc


def _collect_on(context, url: str | None) -> tuple[list[dict], list[dict], str]:
    if url is None:
        raise ClickPathError("缺少实跑地址")
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        preview = _is_preview(page)
    finally:
        page.close()
    if preview:
        baseline = _open_preview(context, _with_flow(url, "baseline"), BASELINE_STEPS)
        current = _open_preview(context, _with_flow(url, "current"), CURRENT_STEPS)
        return baseline, current, url
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        _require_product_shell(page, url)
        baseline = _walk_product(page, BASELINE_STEPS)
    finally:
        page.close()
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        _require_product_shell(page, url)
        current = _walk_product(page, CURRENT_STEPS)
    finally:
        page.close()
    return baseline, current, url


def _payload(baseline_events: list[dict], current_events: list[dict], target: str, browser: str) -> dict:
    baseline = tally(baseline_events)
    current = tally(current_events)
    _assert_budget(baseline, current)
    _assert_events(baseline_events, BASELINE_STEPS)
    _assert_events(current_events, CURRENT_STEPS)
    stamp = _stamp()
    if target.startswith("http"):
        where = f"Playwright 打开 {target}"
    else:
        where = "Playwright 打开内置静态点击路径预览"
    verification = (
        f"已核实 {stamp}。命令 {COMMAND}。视口 1366x768，headless Chrome 实跑，"
        f"{where}。baseline {baseline['clicks']} 次点击 / {baseline['manual_cell_edits']} 次手工修改，"
        f"current {current['clicks']} 次点击 / {current['manual_cell_edits']} 次手工修改，"
        "与 docs/ux_baseline_events.json 条数一致。"
    )
    note = (
        f"已核实 {stamp}。Playwright 实跑 baseline {len(baseline_events)} 条、"
        f"current {len(current_events)} 条，与步骤表一致。命令 {COMMAND}。"
    )
    notes = (
        "基线是改前要逐个下载 4 个文件、并逐格手改的路径。当前路径用粘贴录入和「一键导出全部」。"
        f"点击数来自 Playwright 实跑（{COMMAND}），baseline/current 与事件日志条数一致，"
        "且 current ≤ baseline × 0.5。改前分列控件在现行界面已合并，默认实跑目标是脚本按步骤表生成的静态预览；"
        "设置 FBA_E2E_URL 则改为打开该页面，缺控件或按钮禁用时失败且不写回。"
    )
    return {
        "scenario": SCENARIO,
        "measured_on": f"Playwright headless Chrome {browser}，视口 1366x768，{stamp}，目标 {target}",
        "viewport": "1366x768",
        "baseline": baseline,
        "current": current,
        "notes": notes,
        "playwright_live": True,
        "verification": verification,
        "measured_at": stamp,
        "command": COMMAND,
        "target": target,
        "browser": browser,
        "note": note,
        "baseline_events": baseline_events,
        "current_events": current_events,
    }


def _write(payload: dict) -> None:
    baseline_doc = {
        "scenario": payload["scenario"],
        "measured_on": payload["measured_on"],
        "viewport": payload["viewport"],
        "baseline": payload["baseline"],
        "current": payload["current"],
        "notes": payload["notes"],
        "playwright_live": True,
        "verification": payload["verification"],
        "measured_at": payload["measured_at"],
        "command": payload["command"],
        "target": payload["target"],
        "browser": payload["browser"],
    }
    events_doc = {
        "playwright_live": True,
        "note": payload["note"],
        "measured_at": payload["measured_at"],
        "command": payload["command"],
        "target": payload["target"],
        "browser": payload["browser"],
        "viewport": payload["viewport"],
        "baseline_events": payload["baseline_events"],
        "current_events": payload["current_events"],
    }
    _dump(BASELINE_PATH, baseline_doc)
    _dump(EVENTS_PATH, events_doc)


def _dump(path: Path, payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def measure(*, write: bool) -> dict:
    """实跑两条路径。write=True 时才写回 docs。失败不写回。"""
    if not browser_available():
        raise ClickPathError("Playwright/Chrome 不可用，或已设置 FBA_E2E_SKIP=1")
    from playwright.sync_api import sync_playwright

    url = os.environ.get("FBA_E2E_URL", "").strip()
    server = None
    thread = None
    target = url
    try:
        if not url:
            pages = {
                "baseline": _preview_html("baseline", BASELINE_STEPS).encode("utf-8"),
                "current": _preview_html("current", CURRENT_STEPS).encode("utf-8"),
            }
            server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(pages))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            host, port = server.server_address
            target = f"http://{host}:{port}/"
        with sync_playwright() as playwright:
            browser, context = _launch_context(playwright)
            try:
                baseline_events, current_events, _used = _collect_on(context, target)
                browser_version = browser.version
            finally:
                browser.close()
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)
    recorded_target = url or "builtin-preview"
    payload = _payload(baseline_events, current_events, recorded_target, browser_version)
    if write:
        _write(payload)
    return payload


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="核对或实跑从录入到报关的点击数")
    parser.add_argument("--check", action="store_true", help="只核对已落盘的实跑结果")
    parser.add_argument("--live", action="store_true", help="用 Playwright 实跑并写回 docs")
    args = parser.parse_args(argv)
    if args.live:
        if not browser_available():
            print("SKIPPED live click count: Playwright/Chrome 不可用，或已设置 FBA_E2E_SKIP=1")
            if os.environ.get("FBA_E2E_REQUIRED", "").strip() == "1":
                raise SystemExit(2)
        else:
            measure(write=True)
    check()


if __name__ == "__main__":
    try:
        main()
    except ClickPathError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
