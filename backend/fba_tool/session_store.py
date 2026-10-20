"""任务状态持久化：刷新恢复 + 历史任务库。"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from fba_tool.data_processing import INPUT_COLUMNS, empty_input_df
from fba_tool.invoice_automation import InvoiceDraft, InvoiceField
from fba_tool.app_paths import sessions_dir

SESSIONS_DIR = sessions_dir()
AUTOSAVE_PATH = SESSIONS_DIR / "autosave.json"
HISTORY_INDEX_PATH = SESSIONS_DIR / "history_index.json"
HISTORY_DIR = SESSIONS_DIR / "history"
ROUTING_SNAPSHOTS_DIR = HISTORY_DIR / "routing_snapshots"

PERSIST_KEYS = {
    "task_id",
    "task_name",
    "step",
    "input_df",
    "fnsku_overrides",
    "box_editor_df",
    "box_locked",
    "validation_errors",
    "step4_validated",
    "step4_shipment_bundle",
    "step4_preview_fp",
    "step4_preview_lines",
    "step4_preview_errors",
    "step4_status_lines",
    "step4_validation_errors",
    "step4_factory_long",
    "step4_box_specs",
    "step4_forwarder_df",
    "step4_validated_fp",
    "step4_throw_ratio",
    "invoice_draft",
    "invoice_grid_df",
    "invoice_template_bytes",
    "invoice_active_shipment",
}

SKIP_KEYS = {
    "deepseek_api_key",
    "_store_loaded",
    "_session_hash",
    "_autosave_pending",
}


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dirs() -> None:
    for d in (SESSIONS_DIR, HISTORY_DIR, ROUTING_SNAPSHOTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not HISTORY_INDEX_PATH.exists():
        HISTORY_INDEX_PATH.write_text('{"tasks":[]}', encoding="utf-8")


def _encode_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _decode_bytes(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def _df_to_records(df: pd.DataFrame | None) -> list:
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return []
    return df.where(pd.notna(df), None).to_dict(orient="records")


def _records_to_df(records: list, columns: list[str] | None = None) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=columns or [])
    df = pd.DataFrame(records)
    if columns:
        for col in columns:
            if col not in df.columns:
                df[col] = None
        df = df[columns]
    return df


def _draft_to_dict(draft: InvoiceDraft | None) -> dict | None:
    if draft is None:
        return None
    return {
        "shipment_id": draft.shipment_id,
        "warehouse_code": draft.warehouse_code,
        "template_sheet": draft.template_sheet,
        "fields": [
            {
                "key": f.key,
                "label": f.label,
                "value": f.value,
                "source": f.source,
                "cell": f.cell,
                "required": f.required,
            }
            for f in draft.fields
        ],
    }


def _draft_from_dict(data: dict | None) -> InvoiceDraft | None:
    if not data:
        return None
    fields = [
        InvoiceField(
            key=f["key"],
            label=f["label"],
            value=f.get("value"),
            source=f.get("source", "green"),
            cell=f.get("cell", ""),
            required=bool(f.get("required", False)),
        )
        for f in data.get("fields", [])
    ]
    return InvoiceDraft(
        shipment_id=data.get("shipment_id", ""),
        warehouse_code=data.get("warehouse_code", ""),
        fields=fields,
        template_sheet=data.get("template_sheet", "Sheet1"),
    )


def _serialize_bundle(bundle: list | None) -> list:
    if not bundle:
        return []
    out = []
    for item in bundle:
        out.append(
            {
                "shipment_id": item.get("shipment_id", ""),
                "warehouse": item.get("warehouse", ""),
                "csv_b64": _encode_bytes(item["csv_bytes"]) if item.get("csv_bytes") else "",
                "pdf_b64": _encode_bytes(item["pdf_bytes"]) if item.get("pdf_bytes") else "",
            }
        )
    return out


def _deserialize_bundle(data: list | None) -> list:
    if not data:
        return []
    bundle = []
    for item in data:
        csv_b = _decode_bytes(item["csv_b64"]) if item.get("csv_b64") else None
        pdf_b = _decode_bytes(item["pdf_b64"]) if item.get("pdf_b64") else None
        if csv_b and pdf_b:
            bundle.append(
                {
                    "shipment_id": item.get("shipment_id", ""),
                    "warehouse": item.get("warehouse", ""),
                    "csv_bytes": csv_b,
                    "pdf_bytes": pdf_b,
                }
            )
    return bundle


def auto_task_name(state: dict) -> str:
    ts = datetime.now().strftime("%m-%d %H:%M")
    step = state.get("step", 1)
    sku_n = 0
    df = state.get("input_df")
    if isinstance(df, pd.DataFrame) and not df.empty and "SKU简称" in df.columns:
        sku_n = df["SKU简称"].astype(str).str.strip().replace("", pd.NA).dropna().nunique()
    elif isinstance(df, list) and df:
        sku_n = len({str(r.get("SKU简称", "")).strip() for r in df if r.get("SKU简称")})
    box_n = 0
    box_df = state.get("box_editor_df")
    if isinstance(box_df, pd.DataFrame) and not box_df.empty and "箱号" in box_df.columns:
        box_n = int(box_df["箱号"].astype(int).max())
    elif isinstance(box_df, list) and box_df:
        nums = [int(r.get("箱号", 0) or 0) for r in box_df if r.get("箱号") not in (None, "")]
        box_n = max(nums) if nums else 0
    parts = [ts, f"Step{step}"]
    if sku_n:
        parts.append(f"{sku_n}SKU")
    if box_n:
        parts.append(f"{box_n}箱")
    if state.get("step4_validated"):
        parts.append("已校验")
    return " · ".join(parts)


def snapshot_from_session(session_state) -> dict:
    state: dict[str, Any] = {
        "saved_at": _now_str(),
        "task_id": session_state.get("task_id") or str(uuid.uuid4()),
        "task_name": session_state.get("task_name") or auto_task_name(dict(session_state)),
        "step": int(session_state.get("step", 1)),
    }
    state["input_df"] = _df_to_records(session_state.get("input_df"))
    state["fnsku_overrides"] = dict(session_state.get("fnsku_overrides") or {})
    state["box_editor_df"] = _df_to_records(session_state.get("box_editor_df"))
    state["box_locked"] = bool(session_state.get("box_locked", False))
    state["validation_errors"] = list(session_state.get("validation_errors") or [])

    state["step4_validated"] = bool(session_state.get("step4_validated", False))
    state["step4_shipment_bundle"] = _serialize_bundle(session_state.get("step4_shipment_bundle"))
    state["step4_preview_fp"] = session_state.get("step4_preview_fp", "")
    state["step4_preview_lines"] = list(session_state.get("step4_preview_lines") or [])
    state["step4_preview_errors"] = list(session_state.get("step4_preview_errors") or [])
    state["step4_status_lines"] = list(session_state.get("step4_status_lines") or [])
    state["step4_validation_errors"] = list(session_state.get("step4_validation_errors") or [])
    state["step4_factory_long"] = _df_to_records(session_state.get("step4_factory_long"))
    state["step4_box_specs"] = _df_to_records(session_state.get("step4_box_specs"))
    state["step4_forwarder_df"] = _df_to_records(session_state.get("step4_forwarder_df"))
    state["step4_validated_fp"] = session_state.get("step4_validated_fp", "")
    tr = session_state.get("step4_throw_ratio")
    state["step4_throw_ratio"] = float(tr) if tr is not None else None

    draft = session_state.get("invoice_draft")
    state["invoice_draft"] = _draft_to_dict(draft)
    state["invoice_grid_df"] = _df_to_records(session_state.get("invoice_grid_df"))
    tpl = session_state.get("invoice_template_bytes")
    state["invoice_template_bytes"] = _encode_bytes(tpl) if tpl else ""
    draft_obj = draft if isinstance(draft, InvoiceDraft) else None
    state["invoice_active_shipment"] = draft_obj.shipment_id if draft_obj else ""
    return state


def apply_to_session(session_state, data: dict) -> None:
    session_state.task_id = data.get("task_id") or str(uuid.uuid4())
    session_state.task_name = data.get("task_name") or auto_task_name(data)
    session_state.step = int(data.get("step", 1))

    session_state.input_df = _records_to_df(data.get("input_df") or [], INPUT_COLUMNS)
    if session_state.input_df.empty:
        session_state.input_df = empty_input_df()
    session_state.fnsku_overrides = dict(data.get("fnsku_overrides") or {})
    session_state.box_editor_df = _records_to_df(
        data.get("box_editor_df") or [],
        ["箱号", "来源", "SKU简称", "数量"],
    )
    session_state.box_locked = bool(data.get("box_locked", False))
    session_state.validation_errors = list(data.get("validation_errors") or [])

    session_state.step4_validated = bool(data.get("step4_validated", False))
    session_state.step4_shipment_bundle = _deserialize_bundle(data.get("step4_shipment_bundle"))
    session_state.step4_preview_fp = data.get("step4_preview_fp", "")
    session_state.step4_preview_lines = list(data.get("step4_preview_lines") or [])
    session_state.step4_preview_errors = list(data.get("step4_preview_errors") or [])
    session_state.step4_status_lines = list(data.get("step4_status_lines") or [])
    session_state.step4_validation_errors = list(data.get("step4_validation_errors") or [])
    fl = data.get("step4_factory_long") or []
    session_state.step4_factory_long = pd.DataFrame(fl) if fl else None
    bs = data.get("step4_box_specs") or []
    session_state.step4_box_specs = pd.DataFrame(bs) if bs else None
    fd = data.get("step4_forwarder_df") or []
    session_state.step4_forwarder_df = pd.DataFrame(fd) if fd else None
    session_state.step4_validated_fp = data.get("step4_validated_fp", "")
    tr = data.get("step4_throw_ratio")
    session_state.step4_throw_ratio = float(tr) if tr is not None else None

    session_state.invoice_draft = _draft_from_dict(data.get("invoice_draft"))
    ig = data.get("invoice_grid_df") or []
    session_state.invoice_grid_df = pd.DataFrame(ig) if ig else None
    tpl = data.get("invoice_template_bytes") or ""
    session_state.invoice_template_bytes = _decode_bytes(tpl) if tpl else None
    session_state._session_quick_hash = _quick_session_fp(session_state)
    session_state._session_hash = _state_fingerprint(snapshot_from_session(session_state))


def _state_fingerprint(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _quick_session_fp(session_state) -> str:
    h = hashlib.sha256()
    for key in (
        "task_id",
        "task_name",
        "step",
        "box_locked",
        "step4_validated",
        "step4_validated_fp",
        "step4_preview_fp",
        "step4_throw_ratio",
    ):
        h.update(str(session_state.get(key, "")).encode("utf-8"))
    df = session_state.get("input_df")
    if isinstance(df, pd.DataFrame):
        h.update(df.to_json().encode("utf-8"))
    box = session_state.get("box_editor_df")
    if isinstance(box, pd.DataFrame):
        h.update(box.to_json().encode("utf-8"))
    draft = session_state.get("invoice_draft")
    if draft is not None:
        h.update(str(getattr(draft, "shipment_id", "")).encode("utf-8"))
    grid = session_state.get("invoice_grid_df")
    if isinstance(grid, pd.DataFrame):
        h.update(grid.to_json().encode("utf-8"))
    return h.hexdigest()[:24]


def save_autosave(session_state) -> bool:
    _ensure_dirs()
    quick = _quick_session_fp(session_state)
    if quick == session_state.get("_session_quick_hash"):
        return False
    data = snapshot_from_session(session_state)
    fp = _state_fingerprint(data)
    if session_state.get("_session_hash") == fp:
        session_state._session_quick_hash = quick
        return False
    data["kind"] = "autosave"
    AUTOSAVE_PATH.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    session_state._session_hash = fp
    session_state._session_quick_hash = quick
    return True


def load_autosave() -> dict | None:
    if not AUTOSAVE_PATH.exists():
        return None
    try:
        return json.loads(AUTOSAVE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_history_index() -> dict:
    if not HISTORY_INDEX_PATH.exists():
        return {"tasks": []}
    try:
        return json.loads(HISTORY_INDEX_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tasks": []}


def _save_history_index(index: dict) -> None:
    """先写临时文件再替换，写入中断时原索引仍是可解析 JSON。"""
    _ensure_dirs()
    payload = json.dumps(index, ensure_ascii=False, indent=2)
    tmp = HISTORY_INDEX_PATH.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, HISTORY_INDEX_PATH)


def list_history_tasks(offset: int = 0, limit: int | None = None) -> List[dict]:
    index = _load_history_index()
    tasks = index.get("tasks", [])
    ordered = sorted(tasks, key=lambda x: x.get("updated_at", ""), reverse=True)
    start = max(int(offset or 0), 0)
    if limit is None:
        return ordered[start:]
    return ordered[start:start + max(int(limit), 0)]


def save_history_payload(payload: dict, name: str | None = None) -> str:
    """将工作流快照写入历史库（兼容 Streamlit / React 快照结构）。"""
    _ensure_dirs()
    data = dict(payload)
    task_id = data.get("task_id") or str(uuid.uuid4())
    data["task_id"] = task_id
    if not data.get("task_name"):
        data["task_name"] = auto_task_name(data)
    if name and name.strip():
        data["task_name"] = name.strip()
    data["kind"] = "history"
    data["updated_at"] = _now_str()
    data.setdefault("saved_at", data["updated_at"])
    path = HISTORY_DIR / f"{task_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    index = _load_history_index()
    tasks = [t for t in index.get("tasks", []) if t.get("id") != task_id]
    tasks.append(
        {
            "id": task_id,
            "name": data["task_name"],
            "updated_at": data["updated_at"],
            "step": data.get("step", 1),
            "saved_at": data.get("saved_at", data["updated_at"]),
        }
    )
    index["tasks"] = sorted(tasks, key=lambda x: x.get("updated_at", ""), reverse=True)
    _save_history_index(index)
    return task_id


def load_history_payload(task_id: str) -> dict | None:
    path = HISTORY_DIR / f"{task_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def workflow_payload_has_data(payload: dict) -> bool:
    if payload.get("box_locked") or payload.get("step4_validated"):
        return True
    if payload.get("box_editor_df"):
        return True
    if payload.get("react_step4_ok"):
        return True
    rows = payload.get("input_df") or []
    return any(str(r.get("SKU简称", "")).strip() for r in rows)


def save_history_task(session_state, name: str | None = None) -> str:
    task_id = save_history_payload(snapshot_from_session(session_state), name=name)
    save_autosave(session_state)
    return task_id


def load_history_task(session_state, task_id: str) -> bool:
    path = HISTORY_DIR / f"{task_id}.json"
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        apply_to_session(session_state, data)
        session_state._session_hash = _state_fingerprint(snapshot_from_session(session_state))
        save_autosave(session_state)
        return True
    except Exception:
        return False


def rename_history_task(task_id: str, new_name: str) -> bool:
    path = HISTORY_DIR / f"{task_id}.json"
    if not path.exists() or not new_name.strip():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["task_name"] = new_name.strip()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        index = _load_history_index()
        for t in index.get("tasks", []):
            if t.get("id") == task_id:
                t["name"] = new_name.strip()
                t["updated_at"] = _now_str()
        _save_history_index(index)
        return True
    except Exception:
        return False


def delete_history_task(task_id: str) -> bool:
    path = HISTORY_DIR / f"{task_id}.json"
    if path.exists():
        path.unlink()
    index = _load_history_index()
    index["tasks"] = [t for t in index.get("tasks", []) if t.get("id") != task_id]
    _save_history_index(index)
    return True


def new_blank_session(session_state) -> None:
    """清空并初始化新任务（可选先存入历史）。"""
    keep_api = session_state.get("deepseek_api_key", "")
    for key in list(session_state.keys()):
        del session_state[key]
    session_state.deepseek_api_key = keep_api
    session_state._store_loaded = True
    session_state.task_id = str(uuid.uuid4())
    session_state.task_name = auto_task_name({"step": 1})
    session_state.step = 1
    session_state.input_df = empty_input_df()
    session_state.fnsku_overrides = {}
    session_state.box_editor_df = pd.DataFrame(columns=["箱号", "来源", "SKU简称", "数量"])
    session_state.box_locked = False
    session_state.validation_errors = []
    session_state.step4_validated = False
    session_state.step4_shipment_bundle = None
    session_state.step4_preview_fp = ""
    session_state.step4_preview_lines = []
    session_state.step4_preview_errors = []
    session_state.step4_status_lines = []
    session_state.step4_validation_errors = []
    session_state.step4_factory_long = None
    session_state.step4_box_specs = None
    session_state.step4_forwarder_df = None
    session_state.step4_validated_fp = ""
    session_state.step4_throw_ratio = None
    session_state.invoice_draft = None
    session_state.invoice_grid_df = None
    session_state.invoice_template_bytes = None
    session_state._session_hash = ""
    if AUTOSAVE_PATH.exists():
        AUTOSAVE_PATH.unlink()

# --- Routing Snapshots ---
def save_routing_snapshot(task_id: str, name: str, forwarder_data: List[dict]) -> dict:
    _ensure_dirs()
    snapshot_id = str(uuid.uuid4())
    now_str = _now_str()
    snapshot = {
        "id": snapshot_id,
        "task_id": task_id,
        "name": name.strip() or f"未命名方案-{now_str}",
        "created_at": now_str,
        "forwarder_data": forwarder_data,
    }
    path = ROUTING_SNAPSHOTS_DIR / f"{snapshot_id}.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": snapshot["id"], "name": snapshot["name"], "created_at": snapshot["created_at"]}

def list_routing_snapshots(task_id: str) -> List[dict]:
    if not ROUTING_SNAPSHOTS_DIR.exists():
        return []
    snapshots = []
    for path in ROUTING_SNAPSHOTS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("task_id") == task_id:
                snapshots.append({
                    "id": data.get("id"),
                    "name": data.get("name"),
                    "created_at": data.get("created_at"),
                    "forwarder_data": data.get("forwarder_data"),
                })
        except Exception:
            pass
    # 按时间降序排列
    return sorted(snapshots, key=lambda x: x.get("created_at", ""), reverse=True)

def delete_routing_snapshot(snapshot_id: str) -> bool:
    path = ROUTING_SNAPSHOTS_DIR / f"{snapshot_id}.json"
    if path.exists():
        try:
            path.unlink()
            return True
        except Exception:
            pass
    return False

