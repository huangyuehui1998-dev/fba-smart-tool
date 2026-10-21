"""S5：领星 MCP 定时自动同步（v8 §3.2 第 2 条）。

- asyncio 后台任务，不引入 APScheduler；默认关闭；频率可配（interval_minutes，最少 15 分钟）。
- 与手动“一键拉取”共用同一把锁（SYNC_LOCK），防重入：上一轮没跑完，这一轮记一条“跳过”。
- 失败自动重试（max_retries 次，间隔按 retry_delay_seconds 递增），每次尝试都记到 lingxing_sync_run（trigger/attempt）
  和日志文件 app_data/logs/lingxing_sync.log；全部失败后界面上可以手动“立即重试”。
- 产品库以 MCP 为唯一来源（D-02）：定时同步只写预览里默认勾选的字段。
  手填（manual）字段保持锁定不覆盖。手填售价和领星不同时默认不勾，定时同步不覆盖，预览标出差异；
  用户在预览里勾上后再确认仍会写入（售价不进手填锁）。
  SKU 对不上（sku_mismatch）和报关敏感字段（英文品名/品牌，本地已有值时）不自动写，记为“待人工确认”，留在预览里手动确认。
- 只做只读调用：包一层 ReadOnlyClient，只放行同步用到的查询类 toolId，别的一律拒绝。
- 密钥仍由 lingxing_sync.load_lingxing_settings 读取（DPAPI 密文 mcp_key_enc），日志里只出现掩码。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from typing import Any, Callable, Dict, List, Optional

from fba_tool.sku_keys import SkuCaseConflict

SYNC_LOCK = threading.Lock()

from fba_tool.lingxing_mcp_client import READ_ONLY_TOOLS  # noqa: E402  S9：白名单统一定义在客户端（search 实测 6 个都是 read）

DEFAULTS: Dict[str, Any] = {
    "enabled": False,          # 默认关闭（v8）
    "interval_minutes": 360,
    "max_retries": 3,          # 失败后再试几次（不含第一次）
    "retry_delay_seconds": 60,  # 第 n 次重试前等 n×此值
    "auto_apply": True,        # D-02：定时同步直接按默认勾选写入产品库
}
MIN_INTERVAL = 15
MAX_INTERVAL = 7 * 24 * 60

TRIGGER_SCHEDULED = "scheduled"
TRIGGER_MANUAL_RETRY = "retry"

_state: Dict[str, Any] = {"running": False, "next_run_at": None, "last_result": None, "task": None}
_logger: Optional[logging.Logger] = None


class ReadOnlyViolation(RuntimeError):
    pass


def is_fatal_error(exc: Any) -> bool:
    """不可恢复：白名单拒绝、缺密钥、鉴权失败、未知工具。重试也不会好，直接失败（S5-fix1 第 3 点）。
    S9-step2 M3：只按异常类型判断（LingxingMcpError 子类的 fatal 标志、ReadOnlyViolation），
    不再对服务端原文做子串匹配；传入字符串一律视为可重试。"""
    from fba_tool.lingxing_mcp_client import is_fatal_exception

    if isinstance(exc, ReadOnlyViolation):
        return True
    if isinstance(exc, BaseException):
        return is_fatal_exception(exc)
    return False


class ReadOnlyClient:
    """只放行查询类 toolId 的包装；定时同步不会调用任何写接口。"""

    def __init__(self, inner: Any):
        self._inner = inner
        self.calls: List[str] = []

    violation: Optional[str] = None

    def _check(self, tool_id: str) -> None:
        if tool_id not in READ_ONLY_TOOLS:
            self.violation = f"定时同步只允许只读调用，拒绝 {tool_id}"
            raise ReadOnlyViolation(self.violation)
        self.calls.append(tool_id)

    def initialize(self) -> Any:
        return self._inner.initialize()

    def action(self, tool_id: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self._check(tool_id)
        return self._inner.action(tool_id, params)

    def iter_pages(self, tool_id: str, params: Optional[Dict[str, Any]] = None, **kw: Any):
        self._check(tool_id)
        return self._inner.iter_pages(tool_id, params, **kw)

    def paginate(self, tool_id: str, params: Optional[Dict[str, Any]] = None, **kw: Any):
        self._check(tool_id)
        return self._inner.paginate(tool_id, params, **kw)


# ---------------------------------------------------------------- 日志
def sync_logger() -> logging.Logger:
    global _logger
    from fba_tool.app_paths import logs_dir

    path = logs_dir() / "lingxing_sync.log"
    lg = logging.getLogger("fba.lingxing_sync")
    lg.setLevel(logging.INFO)
    have = [h for h in lg.handlers if isinstance(h, RotatingFileHandler)]
    if not have or getattr(have[0], "baseFilename", "") != str(path):
        for h in have:
            lg.removeHandler(h)
            h.close()
        path.parent.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        lg.addHandler(h)
    _logger = lg
    return lg


def read_log_tail(lines: int = 200) -> List[str]:
    from fba_tool.app_paths import logs_dir

    p = logs_dir() / "lingxing_sync.log"
    if not p.is_file():
        return []
    return p.read_text(encoding="utf-8", errors="replace").splitlines()[-int(lines):]


# ---------------------------------------------------------------- 配置
def load_schedule() -> Dict[str, Any]:
    from fba_tool.lingxing_sync import _read_config

    raw = _read_config().get("auto_sync") or {}
    out = dict(DEFAULTS)
    if isinstance(raw, dict):
        out.update({k: raw[k] for k in DEFAULTS if k in raw})
    return out


def save_schedule(patch: Dict[str, Any]) -> Dict[str, Any]:
    from fba_tool.lingxing_sync import _read_config, _write_config

    cur = load_schedule()
    for k, v in (patch or {}).items():
        if k not in DEFAULTS or v is None:
            continue
        if k in ("enabled", "auto_apply"):
            cur[k] = bool(v)
            continue
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError(f"{k} 应是整数：{v!r}")
        if k == "interval_minutes" and not (MIN_INTERVAL <= n <= MAX_INTERVAL):
            raise ValueError(f"同步间隔应在 {MIN_INTERVAL}–{MAX_INTERVAL} 分钟之间")
        if k == "max_retries" and not (0 <= n <= 10):
            raise ValueError("重试次数应在 0–10 之间")
        if k == "retry_delay_seconds" and not (0 <= n <= 3600):
            raise ValueError("重试间隔应在 0–3600 秒之间")
        cur[k] = n
    data = _read_config()
    data["auto_sync"] = cur
    _write_config(data)
    # 改了开关或间隔都立即重算下次时间（S5-fix1 第 1 点）
    _state["next_run_at"] = compute_next_run(cur) if cur["enabled"] else None
    return cur


CATCH_UP_DELAY_SECONDS = 60  # 启动时已过期：启动后约 1 分钟补跑


def last_success_at() -> Optional[datetime]:
    from fba_tool.master_db import get_last_lingxing_sync_success_at

    ts = get_last_lingxing_sync_success_at()
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def compute_next_run(cfg: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None) -> Optional[str]:
    """下次 = 数据库里上次成功同步时间 + 间隔；从没成功过或已经过期 → 现在 + CATCH_UP_DELAY_SECONDS 补跑一次（S5-fix1 第 2 点）。"""
    cfg = cfg or load_schedule()
    if not cfg["enabled"]:
        return None
    now = now or _now()
    last = last_success_at()
    nxt = last + timedelta(minutes=int(cfg["interval_minutes"])) if last else None
    if nxt is None or nxt <= now:
        nxt = now + timedelta(seconds=CATCH_UP_DELAY_SECONDS)
    return _iso(nxt)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(d: datetime) -> str:
    return d.isoformat()


def status() -> Dict[str, Any]:
    if _state["next_run_at"] is None and load_schedule()["enabled"]:
        _state["next_run_at"] = compute_next_run()
    la = last_success_at()
    return {"running": _state["running"] or SYNC_LOCK.locked(), "next_run_at": _state["next_run_at"],
            "last_success_at": _iso(la) if la else None,
            "last_result": _state["last_result"], "loop_active": bool(_state.get("task")) and not _state["task"].done()}


# ---------------------------------------------------------------- 自动写入（D-02 / D-01）
def auto_apply_preview(run_id: int) -> Dict[str, Any]:
    """按预览默认勾选写入。手填锁定字段跳过。手填售价和领星不同时默认不勾，不自动覆盖。未勾选的记“待人工确认”。"""
    from fba_tool.lingxing_preview import apply_lingxing_field_patch, serialize_preview
    from fba_tool.master_db import add_lingxing_sync_diff, list_lingxing_preview_skus
    import json

    pv = serialize_preview(int(run_id))
    remotes = {r["sku"]: json.loads(r.get("remote_json") or "{}") for r in list_lingxing_preview_skus(int(run_id))}
    stats = {"skus": 0, "written": 0, "locked": 0, "needs_review": 0}
    for kind, items in (pv.get("groups") or {}).items():
        for it in items:
            sku = it["sku"]
            if kind == "sku_mismatch":
                stats["needs_review"] += 1
                add_lingxing_sync_diff(run_id, "needs_review", sku,
                                       f"ASIN 对应的本地 SKU 不一致（{'、'.join(it.get('mismatch_skus') or [])}），不自动写入，请在预览里人工确认")
                continue
            fields = [f["field"] for f in it["fields"] if f["default_checked"]]
            for f in it["fields"]:
                if f.get("locked") and not f["default_checked"] and f["local_value"] != f["remote_value"]:
                    stats["locked"] += 1
                    add_lingxing_sync_diff(run_id, "locked", sku,
                                           f"{f['field']} 是手填值，已锁定，未用领星值覆盖（本地「{f['local_value']}」，领星「{f['remote_value']}」）")
                elif not f["default_checked"] and f["local_value"] != f["remote_value"]:
                    stats["needs_review"] += 1
                    note = f.get("difference") or (
                        f"{f['label']}：本地「{f['local_value']}」→ 领星「{f['remote_value']}」，"
                        "报关敏感/锁定字段不自动写，请人工确认"
                    )
                    add_lingxing_sync_diff(run_id, "needs_review", sku, note)
            if not fields:
                continue
            old = {f["field"]: f["local_value"] for f in it["fields"]}
            new = {f["field"]: f["remote_value"] for f in it["fields"]}
            try:
                res = apply_lingxing_field_patch(sku, fields, remotes.get(sku) or {})
            except SkuCaseConflict as exc:  # S9-step3：SKU 大小写冲突，只跳过这一条，不中断整轮
                add_lingxing_sync_diff(run_id, "sku_case_conflict", sku, f"{exc}，未自动写入")
                continue
            if res["written"]:
                stats["skus"] += 1
            for fld in res["written"]:
                stats["written"] += 1
                add_lingxing_sync_diff(run_id, "applied", sku, f"{fld}：「{old.get(fld, '')}」→「{new.get(fld, '')}」")
            for fld in res["skipped_locked"]:
                stats["locked"] += 1
                add_lingxing_sync_diff(run_id, "locked", sku, f"{fld} 是手填值，已锁定，未用领星值覆盖（领星：「{new.get(fld, '')}」）")
    return stats


# ---------------------------------------------------------------- 一轮同步（含重试）
def run_once(client_factory: Optional[Callable[[], Any]] = None, trigger: str = TRIGGER_SCHEDULED,
             sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """跑一轮：拿不到锁就跳过；失败按配置重试；成功后按 D-02 自动写入。返回摘要（也存到 status().last_result）。"""
    from fba_tool.lingxing_mcp_client import LingxingMcpClient
    from fba_tool.lingxing_sync import iter_full_sync_events, load_lingxing_settings, mask_key
    from fba_tool.master_db import (add_lingxing_sync_diff, create_lingxing_sync_run, finish_lingxing_sync_run,
                                    init_master_db, mark_lingxing_sync_run_status, tag_lingxing_sync_run)

    log = sync_logger()
    cfg = load_schedule()
    init_master_db()
    if not SYNC_LOCK.acquire(blocking=False):
        rid = create_lingxing_sync_run()
        tag_lingxing_sync_run(rid, trigger, 0)
        finish_lingxing_sync_run(rid, "skipped", [], {}, "上一轮同步还没结束，本轮跳过")
        log.info("[%s] 跳过：上一轮同步还没结束（run %s）", trigger, rid)
        res = {"ok": False, "status": "skipped", "run_ids": [rid], "message": "上一轮同步还没结束，本轮跳过"}
        _state["last_result"] = res
        return res
    _state["running"] = True
    run_ids: List[int] = []
    try:
        settings = load_lingxing_settings()
        if not settings["mcp_key"]:
            rid = create_lingxing_sync_run()
            tag_lingxing_sync_run(rid, trigger, 1)
            finish_lingxing_sync_run(rid, "failed", [], {}, "未配置领星 MCP Key")
            log.warning("[%s] 失败：未配置领星 MCP Key（run %s），不重试", trigger, rid)
            res = {"ok": False, "status": "failed", "run_ids": [rid], "message": "未配置领星 MCP Key，请在系统设置中填写"}
            _state["last_result"] = res
            return res
        log.info("[%s] 开始同步，密钥 %s，地址 %s", trigger, mask_key(settings["mcp_key"]), settings["mcp_url"])
        attempts = 1 + int(cfg["max_retries"])
        last_err = ""
        for n in range(1, attempts + 1):
            if n > 1:
                wait = int(cfg["retry_delay_seconds"]) * (n - 1)
                log.info("[%s] 第 %s 次重试，等 %s 秒", trigger, n - 1, wait)
                sleep(wait)
            inner = client_factory() if client_factory else LingxingMcpClient(settings["mcp_key"], settings["mcp_url"])
            client = ReadOnlyClient(inner)
            result: Dict[str, Any] = {}
            err = ""
            fatal = False
            rid: Optional[int] = None
            try:
                for ev in iter_full_sync_events(client=client):
                    if ev.get("event") == "result":
                        result = ev.get("data") or {}
                    elif ev.get("event") == "error":
                        err = ev.get("message") or "领星同步失败"
                        result = ev.get("data") or {}
                        fatal = fatal or bool(ev.get("fatal"))  # 由 iter_full_sync_events 按异常类型给出
            except Exception as exc:  # noqa: BLE001
                err = f"{exc.__class__.__name__}: {exc}"
                fatal = fatal or is_fatal_error(exc)
            rid = result.get("run_id")
            if rid is None:
                rid = create_lingxing_sync_run()
                finish_lingxing_sync_run(rid, "failed", [], {}, err or "领星同步失败")
            rid = int(rid)
            run_ids.append(rid)
            tag_lingxing_sync_run(rid, trigger, n)
            if err:
                last_err = err
                if client.violation and client.violation not in err:
                    err = f"{err}（{client.violation}）"
                log.error("[%s] 第 %s/%s 次失败（run %s）：%s", trigger, n, attempts, rid, err)
                if client.violation or fatal:
                    add_lingxing_sync_diff(rid, "fatal", "", f"不可恢复的错误，不重试：{err}")
                    log.error("[%s] 不可恢复的错误，不重试，已释放锁", trigger)
                    res = {"ok": False, "status": "failed", "fatal": True, "run_ids": run_ids, "attempts": n,
                           "message": f"不可恢复的错误，未重试：{err}"}
                    _state["last_result"] = res
                    return res
                if n < attempts:
                    add_lingxing_sync_diff(rid, "retry", "", f"第 {n}/{attempts} 次失败，将自动重试：{err}")
                continue
            applied: Dict[str, Any] = {}
            if cfg["auto_apply"] and result.get("status") in ("preview_pending", "partial"):
                applied = auto_apply_preview(rid)
                mark_lingxing_sync_run_status(rid, "auto_applied" if result.get("status") == "preview_pending" else "auto_applied_partial")
            log.info("[%s] 第 %s 次成功（run %s）：%s；写入 %s", trigger, n, rid, result.get("counts"), applied or "未自动写入")
            res = {"ok": True, "status": "ok", "run_ids": run_ids, "run_id": rid, "attempts": n,
                   "counts": result.get("counts") or {}, "applied": applied}
            _state["last_result"] = res
            return res
        log.error("[%s] %s 次都失败，放弃；可在界面上点“立即重试”", trigger, attempts)
        res = {"ok": False, "status": "failed", "run_ids": run_ids, "attempts": attempts,
               "message": f"重试 {attempts} 次仍失败：{last_err}"}
        _state["last_result"] = res
        return res
    finally:
        _state["running"] = False
        SYNC_LOCK.release()


# ---------------------------------------------------------------- asyncio 定时循环
async def _loop(tick_seconds: float = 30.0, client_factory: Optional[Callable[[], Any]] = None) -> None:
    while True:
        try:
            cfg = load_schedule()
            if not cfg["enabled"]:
                _state["next_run_at"] = None
            else:
                nxt = _state.get("next_run_at")
                if not nxt:
                    _state["next_run_at"] = compute_next_run(cfg)  # 启动：上次成功 + 间隔；过期则短延迟补跑
                elif _now() >= datetime.fromisoformat(nxt):
                    res = await asyncio.to_thread(run_once, client_factory, TRIGGER_SCHEDULED)
                    cfg2 = load_schedule()
                    # 成功：上次成功 + 间隔；失败/跳过：现在 + 间隔（不在失败后反复补跑）
                    base = (last_success_at() if res.get("ok") else None) or _now()
                    _state["next_run_at"] = _iso(base + timedelta(minutes=int(cfg2["interval_minutes"])))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001  定时器本身不能挂
            sync_logger().exception("定时循环出错：%s", exc)
        await asyncio.sleep(tick_seconds)


def start(tick_seconds: float = 30.0, client_factory: Optional[Callable[[], Any]] = None) -> asyncio.Task:
    t = _state.get("task")
    if t is not None and not t.done():
        return t
    _state["task"] = asyncio.get_running_loop().create_task(_loop(tick_seconds, client_factory))
    return _state["task"]


async def stop() -> None:
    t = _state.get("task")
    _state["task"] = None
    if t is not None and not t.done():
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass


def reset_state() -> None:
    _state.update({"running": False, "next_run_at": None, "last_result": None, "task": None})
