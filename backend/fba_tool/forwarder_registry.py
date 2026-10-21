"""货代档案：模板 xlsx + 列映射，持久化在 app_data/。"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from fba_tool.app_paths import (
    bundled_config_dir,
    bundled_forwarders_templates_dir,
    ensure_app_data_layout,
    resolve_config_read,
    resolve_config_write,
    user_forwarders_templates_dir,
)
from fba_tool.invoice_table import detect_invoice_table_layout
from fba_tool.xlsx_io import load_workbook_fast


@dataclass
class ForwarderProfile:
    id: str
    name: str
    template_file: str
    header_row: int = 1
    first_data_row: int = 2
    column_map: Dict[str, int] = field(default_factory=dict)
    created_at: str = ""
    # S4-fix1：按货代模板导出发票的适配器（send / jiufang）与常量；空 = 只走旧的 ETL 填表
    export_adapter: str = ""
    invoice_export: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _config_path() -> Path:
    ensure_app_data_layout()
    return resolve_config_read("forwarders.json")


def _write_config_path() -> Path:
    ensure_app_data_layout()
    return resolve_config_write("forwarders.json")


def _load_raw() -> Dict[str, Any]:
    path = _config_path()
    if not path.is_file():
        default = bundled_config_dir() / "forwarders.default.json"
        if default.is_file():
            return json.loads(default.read_text(encoding="utf-8"))
        return {"forwarders": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_raw(data: Dict[str, Any]) -> None:
    out = _write_config_path()
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _slug_id(name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", name.strip(), flags=re.UNICODE).strip("-").lower()
    if slug and slug.isascii():
        return slug[:48]
    digest = sha256(name.encode("utf-8")).hexdigest()[:10]
    return f"fwd_{digest}"


def _unique_id(name: str, existing: set[str]) -> str:
    base = _slug_id(name) or "forwarder"
    candidate = base
    n = 2
    while candidate in existing:
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def _template_path(template_file: str) -> Path:
    user = user_forwarders_templates_dir() / template_file
    if user.is_file():
        return user
    bundled = bundled_forwarders_templates_dir() / template_file
    if bundled.is_file():
        return bundled
    raise HTTPException(status_code=404, detail=f"货代模板不存在：{template_file}")


def _detect_layout(template_bytes: bytes, forwarder_id: str | None = None) -> tuple[int, int, Dict[str, int]]:
    from fba_tool.invoice_automation import load_invoice_config

    cfg = load_invoice_config()
    wb = load_workbook_fast(template_bytes)
    layout = detect_invoice_table_layout(wb, cfg=cfg, forwarder_id=forwarder_id)
    if not layout:
        raise HTTPException(status_code=400, detail="无法识别发票表格表头，请确认模板含标准中文列名")
    return layout.header_row, layout.first_data_row, dict(layout.columns)


def list_forwarders() -> List[ForwarderProfile]:
    raw = _load_raw()
    out: List[ForwarderProfile] = []
    seen: set[str] = set()
    for item in raw.get("forwarders", []):
        profile = ForwarderProfile(**item)
        out.append(profile)
        seen.add(profile.id)
    from dataclasses import fields as dataclass_fields

    from fba_tool.invoice_export import export_forwarders

    names = {item.name for item in dataclass_fields(ForwarderProfile)}
    for item in export_forwarders().values():
        fid = str(item.get("id") or "")
        if not fid or fid in seen:
            continue
        payload = {key: value for key, value in item.items() if key in names}
        payload.setdefault("header_row", 1)
        payload.setdefault("first_data_row", 2)
        payload.setdefault("column_map", {})
        payload.setdefault("created_at", "")
        out.append(ForwarderProfile(**payload))
        seen.add(fid)
    return out


def get_forwarder(forwarder_id: str) -> ForwarderProfile:
    for fwd in list_forwarders():
        if fwd.id == forwarder_id:
            return fwd
    raise HTTPException(status_code=404, detail=f"未找到货代：{forwarder_id}")


def get_template_bytes(forwarder_id: str) -> bytes:
    fwd = get_forwarder(forwarder_id)
    return _template_path(fwd.template_file).read_bytes()


def create_forwarder(
    name: str,
    template_bytes: bytes,
    *,
    forwarder_id: str | None = None,
) -> ForwarderProfile:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="货代名称不能为空")
    if not template_bytes:
        raise HTTPException(status_code=400, detail="模板文件为空")

    raw = _load_raw()
    items = raw.setdefault("forwarders", [])
    existing_ids = {str(x.get("id", "")) for x in items}
    fid = forwarder_id.strip() if forwarder_id else _unique_id(name, existing_ids)
    if fid in existing_ids:
        raise HTTPException(status_code=409, detail=f"货代 ID 已存在：{fid}")

    header_row, first_data_row, column_map = _detect_layout(template_bytes, forwarder_id=fid)

    user_forwarders_templates_dir().mkdir(parents=True, exist_ok=True)
    template_file = f"{fid}.xlsx"
    (user_forwarders_templates_dir() / template_file).write_bytes(template_bytes)

    profile = ForwarderProfile(
        id=fid,
        name=name,
        template_file=template_file,
        header_row=header_row,
        first_data_row=first_data_row,
        column_map=column_map,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    items.append(profile.to_dict())
    _save_raw(raw)
    return profile


def update_forwarder(forwarder_id: str, *, name: str | None = None) -> ForwarderProfile:
    raw = _load_raw()
    items = raw.get("forwarders", [])
    for idx, item in enumerate(items):
        if item.get("id") != forwarder_id:
            continue
        if name is not None:
            name = name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="货代名称不能为空")
            item["name"] = name
        _save_raw(raw)
        return ForwarderProfile(**item)
    raise HTTPException(status_code=404, detail=f"未找到货代：{forwarder_id}")


def delete_forwarder(forwarder_id: str) -> None:
    if forwarder_id == "qiluo":
        raise HTTPException(status_code=400, detail="内置货代「琪珞国际」不可删除")
    raw = _load_raw()
    items = raw.get("forwarders", [])
    kept = [x for x in items if x.get("id") != forwarder_id]
    if len(kept) == len(items):
        raise HTTPException(status_code=404, detail=f"未找到货代：{forwarder_id}")
    try:
        fwd = get_forwarder(forwarder_id)
        tpl = user_forwarders_templates_dir() / fwd.template_file
        if tpl.is_file():
            tpl.unlink()
    except HTTPException:
        pass
    raw["forwarders"] = kept
    _save_raw(raw)


def replace_forwarder_template(forwarder_id: str, template_bytes: bytes) -> ForwarderProfile:
    fwd = get_forwarder(forwarder_id)
    header_row, first_data_row, column_map = _detect_layout(template_bytes, forwarder_id=forwarder_id)
    user_forwarders_templates_dir().mkdir(parents=True, exist_ok=True)
    path = user_forwarders_templates_dir() / fwd.template_file
    path.write_bytes(template_bytes)

    raw = _load_raw()
    for item in raw.get("forwarders", []):
        if item.get("id") == forwarder_id:
            item["header_row"] = header_row
            item["first_data_row"] = first_data_row
            item["column_map"] = column_map
            _save_raw(raw)
            return ForwarderProfile(**item)
    raise HTTPException(status_code=404, detail=f"未找到货代：{forwarder_id}")


def decode_template_base64(template_base64: str) -> bytes:
    try:
        return base64.b64decode(template_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"模板 base64 解码失败：{exc}") from exc
