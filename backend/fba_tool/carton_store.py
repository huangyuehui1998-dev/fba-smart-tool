"""箱规库、快照、实测和对比。修改箱规一律新增版本，不改历史行。"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from uuid import uuid4

from fba_tool.carton_math import (
    D,
    box_status,
    chargeable_kg,
    classify_measurements,
    decompose,
    dim_deltas,
    format_volume_bias_pct,
    is_fba_box_id,
    light_heavy_check,
    missing_declared,
    q,
    signed,
    suggest_spec_update,
    summary_lines,
    volumetric_kg,
    volume_of,
    bill_warnings,
    flag_suspected_mixups,
)
from fba_tool.db_backup import backup_reason, utc_now
from fba_tool.db_migrations import is_readonly
from fba_tool.sku_keys import sku_key, sku_text

COMPARE_COLUMNS = ["箱号", "SKU", "申报 L/W/H/kg", "实测 L/W/H/kg", "差值", "体积重差", "计费重差", "状态"]

_LIMITS = {
    "length_cm": (Decimal("0"), Decimal("200"), "箱长(cm)"),
    "width_cm": (Decimal("0"), Decimal("200"), "箱宽(cm)"),
    "height_cm": (Decimal("0"), Decimal("200"), "箱高(cm)"),
    "gross_kg": (Decimal("0"), Decimal("70"), "单箱毛重(kg)"),
    "tare_kg": (Decimal("0"), Decimal("70"), "空箱重(kg)"),
    "unit_kg": (Decimal("0"), Decimal("70"), "单件重(kg)"),
}


class CartonValidationError(ValueError):
    def __init__(self, fields: Dict[str, str]):
        self.fields = fields
        super().__init__("；".join(fields.values()))


class DbNewerError(RuntimeError):
    code = "DB_NEWER_THAN_APP"

    def __init__(self) -> None:
        super().__init__("数据库版本高于当前程序，已只读打开")


def _conn(write: bool = False):
    from fba_tool.master_db import _connect

    if write and is_readonly():
        raise DbNewerError()
    return _connect()


def _ensure_tables(conn) -> None:
    from fba_tool.db_migrations import create_v4_tables

    create_v4_tables(conn)


def _row(conn, sql: str, args: Sequence[Any] = ()) -> Optional[Dict[str, Any]]:
    cur = conn.execute(sql, args)
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([c[0] for c in cur.description], row))


def _rows(conn, sql: str, args: Sequence[Any] = ()) -> List[Dict[str, Any]]:
    cur = conn.execute(sql, args)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _num(value: Any, field: str, fields: Dict[str, str], required: bool = False) -> Optional[Decimal]:
    if value in (None, ""):
        if required:
            fields[field] = f"{_LIMITS.get(field, (0, 0, field))[2]}不能为空"
        return None
    try:
        number = D(value)
    except Exception:
        label = _LIMITS.get(field, (0, 0, field))[2]
        fields[field] = f"{label}不是有效数字"
        return None
    if field in _LIMITS:
        low, high, label = _LIMITS[field]
        if number <= low:
            fields[field] = f"{label}必须大于 0"
            return None
        if number > high:
            unit = "cm" if field.endswith("_cm") else "kg"
            fields[field] = f"{label}不能大于 {high}{unit}"
            return None
    return number


def validate_spec(payload: Dict[str, Any]) -> Dict[str, Any]:
    fields: Dict[str, str] = {}
    sku = sku_text(payload.get("sku"))
    if not sku:
        fields["sku"] = "SKU不能为空"
    spec_name = sku_text(payload.get("spec_name") or "")
    qty_raw = payload.get("qty_per_carton")
    qty: Optional[int] = None
    if qty_raw in (None, ""):
        fields["qty_per_carton"] = "单箱数量不能为空"
    else:
        try:
            qty_num = D(qty_raw)
            if qty_num <= 0 or qty_num != qty_num.to_integral_value():
                fields["qty_per_carton"] = "单箱数量必须是大于 0 的整数"
            else:
                qty = int(qty_num)
        except Exception:
            fields["qty_per_carton"] = "单箱数量不是有效数字"
    length = _num(payload.get("length_cm"), "length_cm", fields, required=True)
    width = _num(payload.get("width_cm"), "width_cm", fields, required=True)
    height = _num(payload.get("height_cm"), "height_cm", fields, required=True)
    gross = _num(payload.get("gross_kg"), "gross_kg", fields, required=True)
    tare = _num(payload.get("tare_kg"), "tare_kg", fields) if payload.get("tare_kg") not in (None, "") else None
    unit = _num(payload.get("unit_kg"), "unit_kg", fields) if payload.get("unit_kg") not in (None, "") else None
    if fields:
        raise CartonValidationError(fields)
    if not spec_name:
        spec_name = f"装量{qty}"
    return {
        "sku": sku,
        "sku_key": sku_key(sku),
        "spec_name": spec_name,
        "length_cm": float(q(length, 2)),
        "width_cm": float(q(width, 2)),
        "height_cm": float(q(height, 2)),
        "qty_per_carton": qty,
        "tare_kg": None if tare is None else float(q(tare, 3)),
        "gross_kg": float(q(gross, 3)),
        "unit_kg": None if unit is None else float(q(unit, 3)),
        "note": sku_text(payload.get("note") or ""),
        "source": sku_text(payload.get("source") or "manual") or "manual",
        "source_ref": sku_text(payload.get("source_ref") or ""),
        "created_by": sku_text(payload.get("created_by") or ""),
    }


def _public(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out["is_default"] = bool(out.get("is_default"))
    return out


def _history(conn, spec_id: Optional[int], sku: str, action: str, before: Any, after: Any) -> None:
    conn.execute(
        """INSERT INTO carton_spec_history (carton_spec_id, sku_key, sku, action, before_json, after_json, created_at)
           VALUES (?,?,?,?,?,?,?)""",
        (
            spec_id,
            sku_key(sku),
            sku,
            action,
            None if before is None else json.dumps(before, ensure_ascii=False, default=str),
            None if after is None else json.dumps(after, ensure_ascii=False, default=str),
            utc_now(),
        ),
    )


def _mirror(conn, spec: Dict[str, Any]) -> None:
    if not spec.get("is_default"):
        return
    conn.execute(
        """UPDATE product_master
           SET carton_length=?, carton_width=?, carton_height=?, qty_per_box=?, carton_gross_weight=?
           WHERE sku=?""",
        (
            spec.get("length_cm"),
            spec.get("width_cm"),
            spec.get("height_cm"),
            spec.get("qty_per_carton"),
            spec.get("gross_kg"),
            spec.get("sku"),
        ),
    )


def _insert_version(conn, data: Dict[str, Any], *, is_default: bool, status: str = "active") -> Dict[str, Any]:
    version = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM carton_spec WHERE sku_key=? AND spec_name=?",
        (data["sku_key"], data["spec_name"]),
    ).fetchone()[0]
    now = utc_now()
    if is_default:
        conn.execute(
            "UPDATE carton_spec SET is_default=0 WHERE sku_key=? AND is_default=1",
            (data["sku_key"],),
        )
    cur = conn.execute(
        """INSERT INTO carton_spec (
            sku_key, sku, spec_name, version, length_cm, width_cm, height_cm, qty_per_carton,
            tare_kg, gross_kg, unit_kg, status, is_default, source, source_ref, note,
            valid_from, valid_to, created_at, created_by
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["sku_key"], data["sku"], data["spec_name"], int(version),
            data["length_cm"], data["width_cm"], data["height_cm"], data["qty_per_carton"],
            data["tare_kg"], data["gross_kg"], data["unit_kg"], status, 1 if is_default else 0,
            data["source"], data["source_ref"], data["note"], now, None, now, data["created_by"],
        ),
    )
    row = _row(conn, "SELECT * FROM carton_spec WHERE id=?", (cur.lastrowid,))
    assert row is not None
    _mirror(conn, row)
    return row


def list_specs(sku: str = "", include_archived: bool = False) -> List[Dict[str, Any]]:
    with _conn() as conn:
        if not is_readonly():
            _ensure_tables(conn)
        sql = "SELECT * FROM carton_spec WHERE 1=1"
        args: List[Any] = []
        if sku:
            sql += " AND sku_key=?"
            args.append(sku_key(sku))
        if not include_archived:
            sql += " AND status!='archived'"
        sql += " ORDER BY sku, spec_name, version"
        return [_public(row) for row in _rows(conn, sql, args)]


def active_specs(sku: str) -> List[Dict[str, Any]]:
    return [row for row in list_specs(sku) if row["status"] == "active"]


def choose_spec(sku: str, qty: Any = None) -> Optional[Dict[str, Any]]:
    specs = active_specs(sku)
    if not specs:
        return None
    if qty not in (None, ""):
        try:
            wanted = int(D(qty))
        except Exception:
            wanted = None
        if wanted:
            for spec in specs:
                if int(spec.get("qty_per_carton") or 0) == wanted:
                    return spec
    for spec in specs:
        if spec.get("is_default"):
            return spec
    return specs[0]


def specs_by_sku(rows: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    found: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        sku = sku_text(row.get("SKU简称") or row.get("sku") or "")
        if not sku or sku in found:
            continue
        specs = active_specs(sku)
        if not specs:
            continue
        found[sku] = [
            {
                "id": spec["id"],
                "spec_name": spec["spec_name"],
                "qty_per_carton": spec["qty_per_carton"],
                "length_cm": spec["length_cm"],
                "width_cm": spec["width_cm"],
                "height_cm": spec["height_cm"],
                "gross_kg": spec["gross_kg"],
                "is_default": spec["is_default"],
            }
            for spec in specs
        ]
    return found


def mixed_spec_notices(rows: Sequence[Dict[str, Any]]) -> List[str]:
    used: Dict[str, set] = {}
    for row in rows:
        sku = sku_text(row.get("SKU简称") or row.get("sku") or "")
        if not sku:
            continue
        qty = row.get("单箱装量") or row.get("qty_per_carton")
        spec = choose_spec(sku, qty)
        if spec:
            used.setdefault(sku, set()).add(int(spec["id"]))
    return [f"本批 SKU {sku} 使用 {len(ids)} 套箱规" for sku, ids in sorted(used.items()) if len(ids) > 1]


def history_for(sku: str) -> List[Dict[str, Any]]:
    with _conn() as conn:
        _ensure_tables(conn)
        return _rows(
            conn,
            "SELECT * FROM carton_spec_history WHERE sku_key=? ORDER BY id",
            (sku_key(sku),),
        )


def create_spec(payload: Dict[str, Any], *, force_default: Optional[bool] = None) -> Dict[str, Any]:
    data = validate_spec(payload)
    with _conn(write=True) as conn:
        _ensure_tables(conn)
        existing = _rows(
            conn,
            "SELECT id FROM carton_spec WHERE sku_key=? AND status='active'",
            (data["sku_key"],),
        )
        is_default = bool(existing) is False if force_default is None else force_default
        if data["source"] == "from_measure_avg":
            is_default = False
        row = _insert_version(conn, data, is_default=is_default)
        _history(conn, row["id"], data["sku"], "create", None, _public(row))
        conn.commit()
        return _public(row)


def replace_spec(spec_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    """任何修改都生成新版本。旧版本改为 superseded。"""
    with _conn(write=True) as conn:
        _ensure_tables(conn)
        current = _row(conn, "SELECT * FROM carton_spec WHERE id=?", (spec_id,))
        if current is None or current["status"] == "archived":
            raise CartonValidationError({"id": "箱规不存在"})
        merged = {**current, **payload, "sku": current["sku"]}
        data = validate_spec(merged)
        data["source"] = payload.get("source") or current["source"]
        conn.execute(
            "UPDATE carton_spec SET status='superseded', valid_to=?, is_default=0 WHERE id=?",
            (utc_now(), spec_id),
        )
        row = _insert_version(conn, data, is_default=bool(current["is_default"]))
        _history(conn, row["id"], data["sku"], "update", _public(current), _public(row))
        conn.commit()
        return _public(row)


def set_default(spec_id: int) -> Dict[str, Any]:
    with _conn(write=True) as conn:
        _ensure_tables(conn)
        current = _row(conn, "SELECT * FROM carton_spec WHERE id=?", (spec_id,))
        if current is None or current["status"] != "active":
            raise CartonValidationError({"id": "只能把在用的箱规设为默认"})
        before = _rows(conn, "SELECT * FROM carton_spec WHERE sku_key=? AND is_default=1", (current["sku_key"],))
        conn.execute("UPDATE carton_spec SET is_default=0 WHERE sku_key=?", (current["sku_key"],))
        conn.execute("UPDATE carton_spec SET is_default=1 WHERE id=?", (spec_id,))
        row = _row(conn, "SELECT * FROM carton_spec WHERE id=?", (spec_id,))
        assert row is not None
        _mirror(conn, row)
        _history(conn, spec_id, row["sku"], "set_default", before, _public(row))
        conn.commit()
        return _public(row)


def archive_spec(spec_id: int) -> Dict[str, Any]:
    with _conn(write=True) as conn:
        _ensure_tables(conn)
        current = _row(conn, "SELECT * FROM carton_spec WHERE id=?", (spec_id,))
        if current is None:
            raise CartonValidationError({"id": "箱规不存在"})
        conn.execute(
            "UPDATE carton_spec SET status='archived', is_default=0, valid_to=? WHERE id=?",
            (utc_now(), spec_id),
        )
        row = _row(conn, "SELECT * FROM carton_spec WHERE id=?", (spec_id,))
        assert row is not None
        if current["is_default"]:
            nxt = _row(
                conn,
                """SELECT * FROM carton_spec WHERE sku_key=? AND status='active' ORDER BY version DESC LIMIT 1""",
                (current["sku_key"],),
            )
            if nxt:
                conn.execute("UPDATE carton_spec SET is_default=1 WHERE id=?", (nxt["id"],))
                mirrored = _row(conn, "SELECT * FROM carton_spec WHERE id=?", (nxt["id"],))
                if mirrored:
                    _mirror(conn, mirrored)
        _history(conn, spec_id, row["sku"], "archive", _public(current), _public(row))
        conn.commit()
        return _public(row)


def _same_numbers(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    keys = ("length_cm", "width_cm", "height_cm", "qty_per_carton", "gross_kg", "tare_kg")
    for key in keys:
        lv, rv = left.get(key), right.get(key)
        if lv in (None, "") and rv in (None, ""):
            continue
        if key == "qty_per_carton":
            if int(lv or 0) != int(rv or 0):
                return False
            continue
        places = 2 if key.endswith("_cm") else 3
        if q(lv or 0, places) != q(rv or 0, places):
            return False
    return True


def preview_import(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    added: List[Dict[str, Any]] = []
    changed: List[Dict[str, Any]] = []
    unchanged = 0
    errors: List[Dict[str, Any]] = []
    for index, raw in enumerate(records, start=2):
        try:
            data = validate_spec(raw)
        except CartonValidationError as exc:
            errors.append({"row": raw.get("row") or index, "fields": exc.fields, "message": str(exc)})
            continue
        current = [
            spec for spec in active_specs(data["sku"])
            if spec["spec_name"] == data["spec_name"]
        ]
        if not current:
            previous = next((spec for spec in active_specs(data["sku"]) if spec.get("is_default")), None)
            added.append({"row": raw.get("row") or index, "new": data, "old": previous})
            continue
        if _same_numbers(current[-1], data):
            unchanged += 1
        else:
            changed.append({"row": raw.get("row") or index, "old": current[-1], "new": data})
    return {"added": added, "changed": changed, "unchanged": unchanged, "errors": errors,
            "added_count": len(added), "changed_count": len(changed)}


def apply_import(records: List[Dict[str, Any]], source_ref: str = "") -> Dict[str, Any]:
    preview = preview_import(records)
    if preview["errors"]:
        raise CartonValidationError({"file": "箱规表有错误，整个文件未写入"})
    backup_reason("carton_import")
    created = []
    for item in preview["added"] + preview["changed"]:
        data = dict(item["new"])
        data["source"] = data.get("source") or "import_xlsx"
        data["source_ref"] = source_ref
        if item in preview["changed"]:
            created.append(replace_spec(int(item["old"]["id"]), data))
        else:
            row = create_spec(data)
            if item.get("old"):
                with _conn(write=True) as conn:
                    _history(conn, row["id"], row["sku"], "import", item["old"], row)
                    conn.commit()
            created.append(row)
    return {"created": created, "added_count": preview["added_count"], "changed_count": preview["changed_count"],
            "unchanged": preview["unchanged"]}


def export_specs_xlsx() -> bytes:
    from openpyxl import Workbook

    rows = list_specs(include_archived=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "箱规"
    headers = ["SKU", "箱规名称", "版本", "箱长(cm)", "箱宽(cm)", "箱高(cm)", "单箱数量", "空箱重", "单箱重(kg)",
               "单件重", "状态", "是否默认", "来源", "备注"]
    ws.append(headers)
    for row in rows:
        ws.append([
            row["sku"], row["spec_name"], row["version"],
            q(row["length_cm"], 2) if row["length_cm"] is not None else None,
            q(row["width_cm"], 2) if row["width_cm"] is not None else None,
            q(row["height_cm"], 2) if row["height_cm"] is not None else None,
            row["qty_per_carton"],
            q(row["tare_kg"], 3) if row["tare_kg"] is not None else None,
            q(row["gross_kg"], 3) if row["gross_kg"] is not None else None,
            q(row["unit_kg"], 3) if row["unit_kg"] is not None else None,
            row["status"], int(bool(row["is_default"])), row["source"], row.get("note") or "",
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_specs_csv() -> bytes:
    rows = list_specs(include_archived=True)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["SKU", "箱规名称", "版本", "箱长(cm)", "箱宽(cm)", "箱高(cm)", "单箱数量", "空箱重", "单箱重(kg)", "来源", "备注"])
    for row in rows:
        writer.writerow([
            row["sku"], row["spec_name"], row["version"],
            f"{q(row['length_cm'], 2):.2f}" if row["length_cm"] is not None else "",
            f"{q(row['width_cm'], 2):.2f}" if row["width_cm"] is not None else "",
            f"{q(row['height_cm'], 2):.2f}" if row["height_cm"] is not None else "",
            row["qty_per_carton"],
            f"{q(row['tare_kg'], 3):.3f}" if row["tare_kg"] is not None else "",
            f"{q(row['gross_kg'], 3):.3f}" if row["gross_kg"] is not None else "",
            row["source"], row.get("note") or "",
        ])
    return buf.getvalue().encode("utf-8-sig")


def zip_app_data(dest: Path) -> Path:
    from fba_tool.app_paths import app_data_dir

    import sqlite3

    root = app_data_dir()
    db_file = root / "fba_master.db"
    if db_file.is_file():
        checkpoint = sqlite3.connect(db_file)
        try:
            checkpoint.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            checkpoint.close()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in list(root.rglob("*")):
            if not path.is_file() or "backups" in path.relative_to(root).parts:
                continue
            if path.name.endswith(("-wal", "-shm")):
                continue
            try:
                zf.write(path, path.relative_to(root).as_posix())
            except FileNotFoundError:
                if path.name.endswith(("-wal", "-shm")):
                    continue
                raise
    return dest


def restore_app_data(zip_path: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise ValueError("只能恢复到空目录")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest)


def record_box_snapshot(fba_id: str, stage: str, boxes: List[Dict[str, Any]], task_id: str = "", batch: str = "") -> Dict[str, Any]:
    if stage not in {"sta_export", "step4_validated"}:
        raise CartonValidationError({"stage": "stage 只能是 sta_export 或 step4_validated"})
    with _conn(write=True) as conn:
        _ensure_tables(conn)
        now = utc_now()
        written = 0
        for box in boxes:
            box_id = str(box.get("fba_box_id") or "").strip().upper()
            if not box_id:
                continue
            conn.execute(
                """INSERT INTO shipment_box_snapshot (
                    fba_id, task_id, batch, box_no, fba_box_id, carton_spec_id, sku_items_json,
                    length_cm, width_cm, height_cm, gross_kg, declared_to_amazon_json, stage, created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(fba_id, fba_box_id, stage) DO UPDATE SET
                    task_id=excluded.task_id,
                    batch=excluded.batch,
                    box_no=excluded.box_no,
                    carton_spec_id=excluded.carton_spec_id,
                    sku_items_json=excluded.sku_items_json,
                    length_cm=excluded.length_cm,
                    width_cm=excluded.width_cm,
                    height_cm=excluded.height_cm,
                    gross_kg=excluded.gross_kg,
                    declared_to_amazon_json=excluded.declared_to_amazon_json
                """,
                (
                    fba_id, task_id, batch, box.get("box_no"), box_id, box.get("carton_spec_id"),
                    json.dumps(box.get("sku_items") or [], ensure_ascii=False),
                    box.get("length_cm"), box.get("width_cm"), box.get("height_cm"), box.get("gross_kg"),
                    json.dumps(box.get("declared_to_amazon") or {}, ensure_ascii=False),
                    stage, now,
                ),
            )
            written += 1
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) FROM shipment_box_snapshot WHERE fba_id=? AND stage=?",
            (fba_id, stage),
        ).fetchone()[0]
        return {"written": written, "count": int(count)}


def snapshot_from_validation(ctx: Dict[str, Any]) -> None:
    result = ctx.get("result")
    if result is not None and not getattr(result, "ok", False):
        return
    parsed = ctx.get("parsed")
    csv_map = getattr(parsed, "csv_map", None) or {}
    batch = resolve_snapshot_batch(ctx)
    for ship in csv_map.values():
        boxes = []
        specs = getattr(ship, "box_specs", None)
        ids = dict(getattr(ship, "box_fba_ids", {}) or {})
        if specs is not None and not getattr(specs, "empty", True):
            from fba_tool.shipment_parser import snapshot_box_id

            for _, spec in specs.iterrows():
                box_no = spec.get("箱号")
                box_id = snapshot_box_id(spec, ids)
                declared = _declared_to_amazon(spec)
                dims = _stored_dims(spec, declared)
                boxes.append({
                    "fba_box_id": box_id,
                    "box_no": box_no,
                    "length_cm": dims["length_cm"],
                    "width_cm": dims["width_cm"],
                    "height_cm": dims["height_cm"],
                    "gross_kg": dims["gross_kg"],
                    "declared_to_amazon": declared,
                })
        if boxes and getattr(ship, "shipment_id", ""):
            record_box_snapshot(
                ship.shipment_id,
                "step4_validated",
                boxes,
                task_id=_task_id(ctx),
                batch=batch,
            )


def _task_id(ctx: Dict[str, Any]) -> str:
    wf = ctx.get("wf") if isinstance(ctx.get("wf"), dict) else {}
    return str(ctx.get("task_id") or wf.get("task_id") or "").strip()


def _batch_in_text(text: str) -> str:
    import re

    found = re.search(r"第\s*(\d+)\s*批", text or "")
    if found:
        return found.group(1)
    found = re.search(r"(?:^|[\\/])batches[\\/](\d+)(?:[\\/]|$)", text or "", re.IGNORECASE)
    if found:
        return found.group(1)
    found = re.search(r"(?:^|[\\/]|^)batch[-_](\d+)(?:[\\/.]|$)", text or "", re.IGNORECASE)
    if found:
        return found.group(1)
    return ""


def _normalize_batch(value: str) -> str:
    import re

    text = str(value or "").strip()
    if not text:
        return ""
    found = _batch_in_text(text)
    if found:
        return found
    if re.fullmatch(r"\d+", text):
        return text
    return ""


def _first_batch(*values: Any) -> str:
    for value in values:
        if isinstance(value, dict):
            for key in ("batch", "batch_id", "batch_no", "批次"):
                found = _normalize_batch(str(value.get(key) or ""))
                if found:
                    return found
            continue
        found = _normalize_batch(str(value or ""))
        if found:
            return found
    return ""


def _batch_from_task_snapshot(task_id: str) -> str:
    if not task_id:
        return ""
    try:
        from fba_tool.session_store import load_history_payload

        payload = load_history_payload(task_id) or {}
    except Exception:
        return ""
    found = _first_batch(payload)
    if found:
        return found
    return _batch_in_text(str(payload.get("task_name") or ""))


def _batch_from_tickets(ctx: Dict[str, Any]) -> str:
    parsed = ctx.get("parsed")
    csv_map = getattr(parsed, "csv_map", None) or {}
    shipment_ids = []
    for ship in csv_map.values():
        shipment_id = str(getattr(ship, "shipment_id", "") or "").strip()
        if shipment_id:
            shipment_ids.append(shipment_id)
    if not shipment_ids:
        return ""
    try:
        from fba_tool.ticket_import import get_ticket
    except Exception:
        return ""
    found = []
    for shipment_id in shipment_ids:
        try:
            ticket = get_ticket(shipment_id) or {}
        except Exception:
            return ""
        batch = _normalize_batch(str(ticket.get("batch") or ""))
        if not batch:
            return ""
        found.append(batch)
    if len(found) == len(shipment_ids) and len(set(found)) == 1:
        return found[0]
    return ""


def _filename_batch(ctx: Dict[str, Any]) -> str:
    parsed = ctx.get("parsed")
    names = list(getattr(parsed, "csv_names", {}).values()) if parsed is not None else []
    wf = ctx.get("wf") if isinstance(ctx.get("wf"), dict) else {}
    names.extend(str(item) for item in (wf.get("source_paths") or []))
    pdf_names = list(getattr(parsed, "pdf_names", {}).values()) if parsed is not None else []
    names.extend(str(item) for item in pdf_names)
    return _batch_in_text(" ".join(str(name) for name in names))


def resolve_snapshot_batch(ctx: Dict[str, Any]) -> str:
    """批次优先取任务快照和 workflow，文件名里的「第N批」只作兜底。"""
    wf = ctx.get("wf") if isinstance(ctx.get("wf"), dict) else {}
    explicit = _first_batch(ctx.get("batch"), wf, wf.get("task") if isinstance(wf.get("task"), dict) else {})
    if explicit:
        return explicit
    task_name = _batch_in_text(str(wf.get("task_name") or ctx.get("task_name") or ""))
    if task_name:
        return task_name
    saved = _batch_from_task_snapshot(_task_id(ctx))
    if saved:
        return saved
    ticket_batch = _batch_from_tickets(ctx)
    if ticket_batch:
        return ticket_batch
    return _filename_batch(ctx)


def _batch_label(ctx: Dict[str, Any]) -> str:
    return resolve_snapshot_batch(ctx)


def _declared_to_amazon(spec: Any) -> Dict[str, Any]:
    declared: Dict[str, Any] = {}
    raw_in = spec.get("declared_in")
    if isinstance(raw_in, list) and len(raw_in) == 3:
        declared["in"] = [raw_in[0], raw_in[1], raw_in[2]]
    raw_lb = spec.get("declared_lb")
    if raw_lb not in (None, ""):
        declared["lb"] = raw_lb
    return declared


def _stored_dims(spec: Any, declared: Dict[str, Any]) -> Dict[str, Any]:
    from fba_tool.carton_math import inches_to_cm_exact, lb_to_kg_exact

    length = spec.get("长(cm)")
    width = spec.get("宽(cm)")
    height = spec.get("高(cm)")
    gross = spec.get("实重(kg)")
    raw_in = declared.get("in")
    if isinstance(raw_in, list) and len(raw_in) == 3:
        length = float(inches_to_cm_exact(raw_in[0]))
        width = float(inches_to_cm_exact(raw_in[1]))
        height = float(inches_to_cm_exact(raw_in[2]))
    if declared.get("lb") not in (None, ""):
        gross = float(lb_to_kg_exact(declared["lb"]))
    return {"length_cm": length, "width_cm": width, "height_cm": height, "gross_kg": gross}


def display_declared(declared: Dict[str, Any]) -> Dict[str, Any]:
    """显示用舍入。库里的厘米和千克保持全精度。"""
    from fba_tool.carton_math import inches_to_cm_exact, lb_to_kg_exact, q

    raw_in = declared.get("in") or []
    cm = [float(q(inches_to_cm_exact(value), 2)) for value in raw_in]
    kg = float(q(lb_to_kg_exact(declared.get("lb") or 0), 3)) if declared.get("lb") not in (None, "") else None
    return {"cm": cm, "kg": kg}


def snapshot_from_editor(fba_id: str, editor_rows: List[Dict[str, Any]], sku_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_box: Dict[str, Dict[str, Any]] = {}
    dims = {str(row.get("SKU简称") or row.get("sku") or ""): row for row in sku_rows}
    for row in editor_rows:
        box_id = str(row.get("FBA箱号") or row.get("fba_box_id") or "").strip().upper()
        if not is_fba_box_id(box_id):
            continue
        slot = by_box.setdefault(box_id, {"fba_box_id": box_id, "box_no": row.get("箱号"), "sku_items": []})
        sku = str(row.get("SKU简称") or "")
        slot["sku_items"].append({"sku": sku, "qty": row.get("数量")})
        master = dims.get(sku) or {}
        slot["length_cm"] = master.get("箱长(cm)") or master.get("length_cm")
        slot["width_cm"] = master.get("箱宽(cm)") or master.get("width_cm")
        slot["height_cm"] = master.get("箱高(cm)") or master.get("height_cm")
        slot["gross_kg"] = master.get("单箱毛重(kg)") or master.get("gross_kg")
    return record_box_snapshot(fba_id, "sta_export", list(by_box.values()))


def import_measurements(rows: List[Dict[str, Any]], *, measured_by: str, source_file: str, batch_id: str = "") -> Dict[str, Any]:
    batch = batch_id or uuid4().hex
    backup_reason("measure_import")
    inserted = 0
    skipped = 0
    issues = [row for row in rows if row.get("kind") == "issue"]
    with _conn(write=True) as conn:
        _ensure_tables(conn)
        now = utc_now()
        waybills = {str(row.get("waybill") or "") for row in rows if row.get("waybill")}
        waybills.discard("")
        for item in waybills:
            conn.execute(
                """DELETE FROM carton_measurement
                   WHERE waybill = ? OR json_extract(raw_json, '$.waybill') = ?""",
                (item, item),
            )
            conn.execute("DELETE FROM forwarder_bill WHERE fba_id = ?", (item,))
        for row in rows:
            if row.get("kind") == "issue":
                continue
            if row.get("kind") == "forwarder_bill":
                conn.execute(
                    """INSERT INTO forwarder_bill (fba_id, forwarder, bill_chargeable_kg, channel_min_kg, source_file, imported_at, import_batch_id)
                       VALUES (?,?,?,?,?,?,?)""",
                    (row.get("fba_id"), row.get("forwarder") or measured_by, row.get("bill_chargeable_kg"),
                     row.get("channel_min_kg"), source_file, now, batch),
                )
                inserted += 1
                continue
            if row.get("kind") == "item":
                digest = _hash({k: row.get(k) for k in ("sku", "marketplace", "longest_cm", "median_cm", "shortest_cm", "weight_kg", "size_tier_amazon")})
                exists = conn.execute("SELECT 1 FROM item_measurement WHERE content_hash=? AND source_file=?", (digest, source_file)).fetchone()
                if exists:
                    skipped += 1
                    continue
                conn.execute(
                    """INSERT INTO item_measurement (
                        sku, asin, marketplace, longest_cm, median_cm, shortest_cm, weight_kg, size_tier_amazon,
                        raw_json, source_file, report_date, imported_at, import_batch_id, content_hash
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        row.get("sku"), row.get("asin"), (row.get("marketplace") or "US").upper(),
                        row.get("longest_cm"), row.get("median_cm"), row.get("shortest_cm"), row.get("weight_kg"),
                        row.get("size_tier"), json.dumps(row.get("raw") or {}, ensure_ascii=False), source_file,
                        row.get("report_date"), now, batch, digest,
                    ),
                )
                inserted += 1
                continue
            digest = _hash({
                "measured_by": measured_by,
                "fba_box_id": str(row.get("fba_box_id") or "").upper(),
                "weight_kg": row.get("weight_kg"),
                "length_cm": row.get("length_cm"),
                "width_cm": row.get("width_cm"),
                "height_cm": row.get("height_cm"),
                "source_row": row.get("source_row"),
            })
            exists = conn.execute(
                "SELECT 1 FROM carton_measurement WHERE content_hash=? AND source_file=?",
                (digest, source_file),
            ).fetchone()
            fba_id, waybill = _stored_ticket_ids(row)
            if exists:
                if fba_id or waybill:
                    conn.execute(
                        """UPDATE carton_measurement
                           SET fba_id = CASE WHEN fba_id IS NULL OR fba_id = '' THEN ? ELSE fba_id END,
                               waybill = CASE WHEN waybill IS NULL OR waybill = '' THEN ? ELSE waybill END
                           WHERE content_hash = ? AND source_file = ?""",
                        (fba_id, waybill, digest, source_file),
                    )
                skipped += 1
                continue
            status = "invalid_id" if not is_fba_box_id(row.get("fba_box_id")) else ""
            conn.execute(
                """INSERT INTO carton_measurement (
                    fba_id, waybill, fba_box_id, box_no, sku_key, measured_by, length_cm, width_cm, height_cm,
                    weight_kg, chargeable_kg, raw_unit, raw_json, source_file, source_row, measured_at,
                    imported_at, import_batch_id, match_status, content_hash
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    fba_id, waybill, str(row.get("fba_box_id") or ""), row.get("box_no"),
                    sku_key(row.get("sku") or ""), measured_by, row.get("length_cm"), row.get("width_cm"),
                    row.get("height_cm"), row.get("weight_kg"), row.get("chargeable_kg"), row.get("raw_unit"),
                    json.dumps(row.get("raw") or {}, ensure_ascii=False), source_file, row.get("source_row"),
                    row.get("measured_at"), now, batch, status, digest,
                ),
            )
            inserted += 1
        conn.commit()
    return {"import_batch_id": batch, "inserted": inserted, "skipped": skipped, "issues": issues}


def delete_import_batch(batch_id: str) -> Dict[str, int]:
    with _conn(write=True) as conn:
        _ensure_tables(conn)
        counts = {}
        for table in ("carton_measurement", "item_measurement", "forwarder_bill"):
            cur = conn.execute(f"DELETE FROM {table} WHERE import_batch_id=?", (batch_id,))
            counts[table] = cur.rowcount
        conn.commit()
        return counts


def assign_measurement(measurement_id: int, fba_box_id: str) -> Dict[str, Any]:
    target = str(fba_box_id or "").strip().upper()
    if not is_fba_box_id(target):
        raise CartonValidationError({"fba_box_id": "手工指定的箱号必须是完整的 FBA 箱号"})
    with _conn(write=True) as conn:
        _ensure_tables(conn)
        conn.execute(
            "UPDATE carton_measurement SET manual_box_id=?, match_status='matched' WHERE id=?",
            (target, measurement_id),
        )
        row = _row(conn, "SELECT * FROM carton_measurement WHERE id=?", (measurement_id,))
        conn.commit()
        if row is None:
            raise CartonValidationError({"id": "实测行不存在"})
        return row


def _snapshots(conn, fba_id: str, batch: str) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM shipment_box_snapshot WHERE 1=1"
    args: List[Any] = []
    if fba_id:
        sql += " AND fba_id=?"
        args.append(fba_id)
    if batch:
        sql += " AND batch=?"
        args.append(batch)
    sql += " ORDER BY id"
    rows = _rows(conn, sql, args)
    # 同一箱号保留最后一次快照
    chosen: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        chosen[str(row["fba_box_id"]).upper()] = row
    return list(chosen.values())


def _measurements(conn, fba_id: str, source: str) -> List[Dict[str, Any]]:
    sql = "SELECT * FROM carton_measurement WHERE 1=1"
    args: List[Any] = []
    if fba_id:
        sql += " AND (fba_id=? OR fba_id IS NULL OR fba_id='')"
        args.append(fba_id)
    if source:
        sql += " AND measured_by=?"
        args.append(source)
    return _rows(conn, sql, args)


def compare_carton(fba_id: str = "", batch: str = "", source: str = "", threshold: Any = None) -> Dict[str, Any]:
    from fba_tool.carton_policy import dim_divisor, source_label

    measured_by = source or "forwarder_jiufang"
    divisor = dim_divisor(measured_by)
    with _conn() as conn:
        if not is_readonly():
            _ensure_tables(conn)
        declared_rows = _snapshots(conn, fba_id, batch)
        measured_rows = _measurements(conn, fba_id, measured_by)
        bills = _rows(
            conn,
            "SELECT * FROM forwarder_bill WHERE (?='' OR fba_id=?)",
            (fba_id, fba_id),
        )
    if not declared_rows:
        return {
            "mode": "ticket_only",
            "message": "尚无申报快照，请先完成第 4 步校验",
            "columns": COMPARE_COLUMNS,
            "rows": [],
            "quality": [],
            "summary": {},
            "dim_divisor": float(divisor),
            "dim_source_label": source_label(measured_by),
        }
    if not measured_rows:
        declared_sum = sum((q(row.get("gross_kg") or 0, 3) for row in declared_rows), Decimal("0"))
        bill_sum = sum((q(row.get("bill_chargeable_kg") or 0, 2) for row in bills), Decimal("0"))
        summary: Dict[str, Any] = {}
        if declared_rows and bills:
            ticket_delta = q(bill_sum - declared_sum, 2)
            summary = {
                "ticket_delta": float(ticket_delta),
                "headline": f"整票差值 {signed(ticket_delta)}kg",
                "scope_note": "整票口径",
            }
        return {
            "mode": "ticket_only",
            "message": "只有整票数据",
            "columns": COMPARE_COLUMNS,
            "rows": [],
            "quality": [],
            "summary": summary,
            "dim_divisor": float(divisor),
            "dim_source_label": source_label(measured_by),
        }
    declared_by_id = {str(row["fba_box_id"]).upper(): row for row in declared_rows}
    measured_ids = [str(row.get("manual_box_id") or row.get("fba_box_id") or "") for row in measured_rows]
    statuses = classify_measurements(declared_by_id.keys(), measured_ids)
    for row, status, used_id in zip(measured_rows, statuses, measured_ids):
        if row.get("manual_box_id"):
            row["match_status"] = "matched"
            row["_used_id"] = str(row["manual_box_id"]).upper()
        else:
            row["match_status"] = status
            row["_used_id"] = used_id.upper()
    duplicate_ids = sorted({row["_used_id"] for row in measured_rows if row["match_status"] == "duplicate"})
    main = []
    quality = []
    matched_for_math = []
    for row in measured_rows:
        if row["match_status"] != "matched":
            quality.append(_quality_row(row))
            continue
        declared = declared_by_id.get(row["_used_id"])
        if declared is None:
            row["match_status"] = "unmatched"
            quality.append(_quality_row(row))
            continue
        built = _compare_row(declared, row, divisor)
        main.append(built["view"])
        matched_for_math.append(built["math"])
    missing = missing_declared(declared_by_id.keys(), [row["_used_id"] for row in measured_rows if row["match_status"] != "invalid_id"])
    for box_id in missing:
        quality.append({"kind": "无过机记录", "fba_box_id": box_id, "match_status": "missing"})
    tickets, unmatched_bills = _tickets_for_carry(measured_rows, bills, divisor)
    for bill in unmatched_bills:
        quality.append({
            "kind": "账单无对应过机行",
            "match_status": "账单无对应过机行",
            "fba_box_id": bill.get("fba_id"),
            "fba_id": bill.get("fba_id"),
            "bill_kg": float(q(bill.get("bill_kg") or 0, 2)),
            "message": "该票没有对应过机行，未把整票账单计入进位",
        })
    parts = decompose(matched_for_math, tickets, divisor)
    lines = summary_lines(parts, len(main), duplicate_ids)
    if unmatched_bills:
        names = "、".join(str(bill.get("fba_id") or "") for bill in unmatched_bills)
        lines["unmatched_bills"] = f"{names} 无对应过机行，未计入进位"
    bias = suggest_spec_update(matched_for_math)
    volumes = []
    for item in matched_for_math:
        base = volume_of(item["declared_dims"])
        if base:
            volumes.append((volume_of(item["measured_dims"]) - base) / base)
    mean_ratio = (sum(volumes) / Decimal(len(volumes))) if volumes else Decimal("0")
    declared_weights = [row.get("gross_kg") or 0 for row in declared_rows]
    conservation = light_heavy_check(declared_weights, [{"weight_kg": row.get("weight_kg") or 0, "match_status": row["match_status"]} for row in measured_rows], threshold)
    return {
        "mode": "box",
        "message": "",
        "columns": COMPARE_COLUMNS,
        "rows": main,
        "quality": quality,
        "duplicate_ids": duplicate_ids,
        "summary": {
            **{key: float(value) for key, value in parts.items()},
            **lines,
            "deduped_count": len(main),
            "measured_count": len(measured_rows),
            "scope_note": f"去重 {len(main)} 箱" if main else "",
            "carry_scope": "按票匹配",
            "unmatched_bills": [bill.get("fba_id") for bill in unmatched_bills],
            "suggest_update": bias,
            "suggest_text": "建议更新箱规库 / STA 箱规" if bias else "",
            "volume_bias_pct": format_volume_bias_pct(mean_ratio) if volumes else "",
        },
        "conservation": conservation,
        "bill_warnings": bill_warnings(tickets, divisor),
        "suspected": flag_suspected_mixups([
            {"id": row.get("fba_box_id"), "sku": row.get("sku_key") or "", "weight_kg": row.get("weight_kg") or 0}
            for row in measured_rows
        ]),
        "dim_divisor": float(divisor),
        "dim_source_label": source_label(measured_by),
    }


def _quality_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": row["match_status"],
        "fba_box_id": row.get("fba_box_id"),
        "match_status": row["match_status"],
        "weight_kg": row.get("weight_kg"),
        "id": row.get("id"),
    }


def _compare_row(declared: Dict[str, Any], measured: Dict[str, Any], divisor) -> Dict[str, Any]:
    items = []
    try:
        items = json.loads(declared.get("sku_items_json") or "[]")
    except json.JSONDecodeError:
        items = []
    sku = "、".join(str(item.get("sku") or "") for item in items if item.get("sku")) or measured.get("sku_key") or ""
    decl_dims = [declared.get("length_cm") or 0, declared.get("width_cm") or 0, declared.get("height_cm") or 0]
    meas_dims = [measured.get("length_cm") or 0, measured.get("width_cm") or 0, measured.get("height_cm") or 0]
    deltas = dim_deltas(decl_dims, meas_dims)
    decl_vol = volumetric_kg(*decl_dims, divisor)
    meas_vol = volumetric_kg(*meas_dims, divisor)
    decl_cw = chargeable_kg(declared.get("gross_kg") or 0, decl_dims, divisor)
    meas_cw = chargeable_kg(measured.get("weight_kg") or 0, meas_dims, divisor)
    status = box_status(decl_dims, meas_dims, declared.get("gross_kg") or 0, measured.get("weight_kg") or 0, divisor)
    delta_text = " / ".join(signed(item) for item in deltas)
    view = {
        "箱号": measured.get("manual_box_id") or measured.get("fba_box_id"),
        "SKU": sku,
        "申报 L/W/H/kg": _dims_text(decl_dims, declared.get("gross_kg")),
        "实测 L/W/H/kg": _dims_text(meas_dims, measured.get("weight_kg")),
        "差值": delta_text,
        "体积重差": signed(meas_vol - decl_vol),
        "计费重差": signed(meas_cw - decl_cw),
        "状态": status,
        "status_class": "text-red-600" if status == "异常" else "",
    }
    math = {
        "declared_dims": decl_dims,
        "measured_dims": meas_dims,
        "declared_kg": declared.get("gross_kg") or 0,
        "measured_kg": measured.get("weight_kg") or 0,
    }
    return {"view": view, "math": math}


def _dims_text(dims: Sequence[Any], kg: Any) -> str:
    return " / ".join([f"{q(item, 2):.2f}" for item in dims] + [f"{q(kg or 0, 3):.3f}"])


def _stored_ticket_ids(row: Dict[str, Any]) -> tuple[str, str]:
    waybill = str(row.get("waybill") or "").strip()
    raw = row.get("raw")
    if not waybill and isinstance(raw, dict):
        waybill = str(raw.get("waybill") or "").strip()
    fba_id = str(row.get("fba_id") or "").strip() or waybill
    return fba_id, waybill


def _measurement_ticket_id(row: Dict[str, Any]) -> str:
    fba_id, waybill = _stored_ticket_ids(row)
    if fba_id:
        return fba_id
    if waybill:
        return waybill
    raw_json = row.get("raw_json")
    if isinstance(raw_json, str) and raw_json.strip():
        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError:
            payload = {}
        text = str((payload or {}).get("waybill") or "").strip()
        if text:
            return text
    return ""


def _tickets_for_carry(
    measured_rows: List[Dict[str, Any]],
    bills: List[Dict[str, Any]],
    divisor,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    del divisor
    by_fba: Dict[str, List[Dict[str, Any]]] = {}
    for row in measured_rows:
        dims = [row.get("length_cm") or 0, row.get("width_cm") or 0, row.get("height_cm") or 0]
        entry: Dict[str, Any] = {
            "weight_kg": row.get("weight_kg") or 0,
            "chargeable_kg": row.get("chargeable_kg"),
        }
        if any(D(item) > 0 for item in dims):
            entry["dims"] = dims
        by_fba.setdefault(_measurement_ticket_id(row), []).append(entry)
    matched: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []
    for bill in bills:
        key = str(bill.get("fba_id") or "").strip()
        rows = by_fba.get(key) or []
        ticket = {
            "fba_id": key,
            "bill_kg": bill.get("bill_chargeable_kg") or 0,
            "rows": rows,
        }
        if rows:
            matched.append(ticket)
        else:
            unmatched.append(ticket)
    return matched, unmatched


def compare_export_xlsx(fba_id: str = "", batch: str = "", source: str = "") -> bytes:
    from openpyxl import Workbook

    report = compare_carton(fba_id, batch, source)
    wb = Workbook()
    ws = wb.active
    ws.title = "箱规对比"
    ws.append(report["columns"])
    for row in report["rows"]:
        ws.append([row.get(column) for column in report["columns"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def compare_items(batch: str = "", marketplace: str = "US") -> Dict[str, Any]:
    from fba_tool.carton_policy import item_policy
    from fba_tool.master_db import get_product_by_sku

    market = (marketplace or "US").upper()
    policy = item_policy()
    with _conn() as conn:
        _ensure_tables(conn)
        sql = "SELECT * FROM item_measurement WHERE marketplace=?"
        args: List[Any] = [market]
        if batch:
            sql += " AND import_batch_id=?"
            args.append(batch)
        fees = _rows(conn, sql, args)
    rows = []
    for fee in fees:
        master = get_product_by_sku(fee.get("sku") or "") or {}
        our_tier = _our_size_tier(master)
        fee_tier = str(fee.get("size_tier_amazon") or "")
        status = "一致" if our_tier and our_tier == fee_tier else ("分段不一致" if our_tier and fee_tier and _tier_rank(fee_tier) > _tier_rank(our_tier) else ("分段不一致" if our_tier and fee_tier and our_tier != fee_tier else "一致"))
        weight = D(fee.get("weight_kg") or 0)
        boundary = D(policy["next_weight_boundary_kg"])
        margin = None
        margin_text = ""
        if boundary > weight > 0:
            margin = (boundary - weight) / boundary * Decimal("100")
            if margin < D(policy["cross_tier_margin_pct"]):
                margin_text = f"临界，距下一档 {q(margin, 1):.1f}%"
                if status == "一致":
                    status = "临界"
        guide = ""
        if status == "分段不一致":
            guide = policy["remeasure_guide"]
        rows.append({
            "sku": fee.get("sku"),
            "marketplace": market,
            "status": status,
            "our_tier": our_tier,
            "fee_tier": fee_tier,
            "margin_text": margin_text,
            "guide": guide,
            "reimbursement": policy["reimbursement_text"] if status == "分段不一致" else "",
        })
    return {"marketplace": market, "rows": rows, "policy": policy}


def _our_size_tier(master: Dict[str, Any]) -> str:
    if master.get("size_tier"):
        return str(master["size_tier"])
    raw = master.get("extra_data")
    if isinstance(raw, str) and raw.strip().startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        return str(data.get("size_tier") or "")
    return ""


def _tier_rank(name: str) -> int:
    order = ["small standard", "large standard", "small oversize", "large bulky", "extra large", "special oversize"]
    key = name.strip().lower()
    return order.index(key) if key in order else 0


def create_measured_average(sku: str, dims: Sequence[Any], gross_kg: Any, qty: int, spec_name: str = "") -> Dict[str, Any]:
    return create_spec(
        {
            "sku": sku,
            "spec_name": spec_name or "实测均值",
            "length_cm": dims[0],
            "width_cm": dims[1],
            "height_cm": dims[2],
            "qty_per_carton": qty,
            "gross_kg": gross_kg,
            "source": "from_measure_avg",
        },
        force_default=False,
    )


def count_products_and_specs(db_file: Path) -> Dict[str, int]:
    import sqlite3

    conn = sqlite3.connect(db_file)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        products = int(conn.execute("SELECT COUNT(*) FROM product_master").fetchone()[0]) if "product_master" in tables else 0
        specs = int(conn.execute("SELECT COUNT(*) FROM carton_spec").fetchone()[0]) if "carton_spec" in tables else 0
        return {"products": products, "carton_specs": specs}
    finally:
        conn.close()
