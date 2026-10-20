"""出口商档案 — 持久化 app_data/config/exporter_profiles.json。"""
from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from fba_tool.app_paths import bundled_config_dir, ensure_app_data_layout, resolve_config_read, resolve_config_write


def _config_path() -> Path:
    ensure_app_data_layout()
    return resolve_config_read("exporter_profiles.json")


def _write_path() -> Path:
    ensure_app_data_layout()
    return resolve_config_write("exporter_profiles.json")


def _load_raw() -> Dict[str, Any]:
    path = _config_path()
    if not path.is_file():
        default = bundled_config_dir() / "exporter_profiles.default.json"
        if default.is_file():
            return json.loads(default.read_text(encoding="utf-8"))
        return {"active_id": "", "profiles": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_raw(data: Dict[str, Any]) -> None:
    out = _write_path()
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _slug_id(name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", name.strip(), flags=re.UNICODE).strip("-").lower()
    if slug and slug.isascii():
        return slug[:48]
    return f"exp_{sha256(name.encode('utf-8')).hexdigest()[:10]}"


def list_profiles() -> List[Dict[str, Any]]:
    raw = _load_raw()
    active = raw.get("active_id", "")
    out = []
    for p in raw.get("profiles", []):
        item = dict(p)
        item["is_active"] = item.get("id") == active
        out.append(item)
    return out


def get_profile(profile_id: str) -> Dict[str, Any]:
    for p in list_profiles():
        if p.get("id") == profile_id:
            return p
    raise HTTPException(status_code=404, detail=f"未找到出口商：{profile_id}")


def get_active_profile() -> Dict[str, Any]:
    raw = _load_raw()
    active_id = raw.get("active_id", "")
    if active_id:
        try:
            return get_profile(active_id)
        except HTTPException:
            pass
    profiles = raw.get("profiles") or []
    if profiles:
        return dict(profiles[0])
    raise HTTPException(status_code=404, detail="尚未配置出口商档案")


def upsert_profile(data: Dict[str, Any]) -> Dict[str, Any]:
    raw = _load_raw()
    profiles: List[Dict[str, Any]] = list(raw.get("profiles") or [])
    pid = str(data.get("id") or "").strip()
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="出口商名称不能为空")
    if not pid:
        existing = {p.get("id") for p in profiles}
        pid = _slug_id(name)
        n = 2
        base = pid
        while pid in existing:
            pid = f"{base}_{n}"
            n += 1

    payload = {
        "id": pid,
        "name": name,
        "credit_code": str(data.get("credit_code") or "").strip(),
        "address": str(data.get("address") or "").strip(),
        "tel": str(data.get("tel") or "").strip(),
        "signed_at": str(data.get("signed_at") or "武汉").strip() or "武汉",
        "domestic_source": str(data.get("domestic_source") or "武汉").strip() or "武汉",
    }

    replaced = False
    for i, p in enumerate(profiles):
        if p.get("id") == pid:
            profiles[i] = payload
            replaced = True
            break
    if not replaced:
        profiles.append(payload)

    if not raw.get("active_id"):
        raw["active_id"] = pid
    raw["profiles"] = profiles
    _save_raw(raw)
    return get_profile(pid)


def delete_profile(profile_id: str) -> None:
    raw = _load_raw()
    profiles = [p for p in raw.get("profiles") or [] if p.get("id") != profile_id]
    if len(profiles) == len(raw.get("profiles") or []):
        raise HTTPException(status_code=404, detail=f"未找到出口商：{profile_id}")
    raw["profiles"] = profiles
    if raw.get("active_id") == profile_id:
        raw["active_id"] = profiles[0]["id"] if profiles else ""
    _save_raw(raw)


def set_active(profile_id: str) -> Dict[str, Any]:
    get_profile(profile_id)
    raw = _load_raw()
    raw["active_id"] = profile_id
    _save_raw(raw)
    return get_profile(profile_id)
