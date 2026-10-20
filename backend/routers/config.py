"""系统配置、模板与历史测试文件。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse

from fba_tool.data_processing import INPUT_COLUMNS
from fba_tool.history_files import (
    history_dir,
    list_history_files,
    read_history_file_bytes,
    resolve_history_file,
)
from fba_tool.template_loader import list_user_templates, read_template_headers, templates_dir
from fba_tool.user_config import (
    load_formulas,
    load_settings,
    reset_all_to_defaults,
    save_formulas,
    save_settings,
    throw_ratio,
    weight_limit_kg,
)
from fba_tool.exporter_profiles import delete_profile, list_profiles, set_active, upsert_profile
from schemas import FormulasUpdateRequest, SettingsUpdateRequest
from schemas.customs import ExporterActiveBody, ExporterProfileBody
from utils.responses import attachment_disposition, file_response

router = APIRouter()


def _safe_template_filename(name: str) -> str:
    safe = Path(name).name
    if not safe or safe.startswith(".") or ".." in name:
        raise HTTPException(status_code=400, detail="无效的文件名")
    return safe


@router.get("/api/config/settings")
def get_settings(response: Response):
    data = load_settings()
    _flag(response)
    return data


@router.put("/api/config/settings")
def update_settings(body: SettingsUpdateRequest):
    save_settings(body.settings)
    return {"ok": True, "settings": load_settings(force=True)}


@router.get("/api/config/formulas")
def get_formulas(response: Response):
    data = load_formulas()
    _flag(response)
    return data


def _flag(response: Response) -> None:
    from urllib.parse import quote

    from fba_tool.user_config import config_errors

    errs = config_errors()
    if errs:
        response.headers["X-Config-Warning"] = quote("；".join(errs.values()))


@router.get("/api/config/errors")
def get_config_errors():
    """坏 JSON 的用户配置（user_settings.json / formulas.json）：界面顶部据此显示黄色提示（S7-fix1）。"""
    from fba_tool.user_config import config_errors

    load_settings(force=True)  # 重新读一遍：用户改好文件后提示自动消失
    load_formulas(force=True)
    errs = config_errors()
    return {"ok": not errs, "errors": [{"file": k, "message": v} for k, v in errs.items()]}


@router.put("/api/config/formulas")
def update_formulas(body: FormulasUpdateRequest):
    save_formulas(body.formulas)
    return {"ok": True, "formulas": load_formulas(force=True)}


@router.post("/api/config/reset")
def reset_config():
    reset_all_to_defaults()
    return {
        "ok": True,
        "settings": load_settings(force=True),
        "formulas": load_formulas(force=True),
    }


@router.get("/api/exporters")
def api_list_exporters():
    return {"profiles": list_profiles()}


@router.put("/api/exporters/{profile_id}")
def api_upsert_exporter(profile_id: str, body: ExporterProfileBody):
    payload = body.model_dump()
    payload["id"] = profile_id
    profile = upsert_profile(payload)
    return {"ok": True, "profile": profile}


@router.delete("/api/exporters/{profile_id}")
def api_delete_exporter(profile_id: str):
    delete_profile(profile_id)
    return {"ok": True}


@router.post("/api/exporters/active")
def api_set_active_exporter(body: ExporterActiveBody):
    profile = set_active(body.id)
    return {"ok": True, "profile": profile}


@router.get("/api/templates")
def list_templates():
    return {
        "templates_dir": str(templates_dir()),
        "files": list_user_templates(),
    }


@router.get("/api/templates/preview")
def preview_template(name: str):
    """预览模板表头（前若干行）。"""
    filename = _safe_template_filename(name)
    path = templates_dir() / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"模板不存在：{filename}")
    headers = read_template_headers(filename, max_rows=8)
    return {"filename": filename, "headers": headers}


@router.get("/api/history/files")
def api_history_files():
    """Step 4 历史测试 CSV/PDF 列表（扫描 templates/ 与 history/）。"""
    data = list_history_files()
    return {**data, "history_dir": str(history_dir())}


@router.get("/api/history/files/download")
def api_history_file_download(kind: str, name: str):
    """下载单个历史测试文件，供前端构造 File 对象。"""
    kind_norm = kind.lower().strip()
    if kind_norm not in ("csv", "pdf"):
        raise HTTPException(status_code=400, detail="kind 须为 csv 或 pdf")
    safe_name = _safe_template_filename(name)
    media = "text/csv" if kind_norm == "csv" else "application/pdf"
    path = resolve_history_file(kind_norm, safe_name)
    if path is not None:
        return FileResponse(
            path,
            media_type=media,
            filename=safe_name,
            headers={
                "Content-Disposition": attachment_disposition(safe_name),
                "Cache-Control": "private, max-age=3600",
            },
        )
    raw = read_history_file_bytes(kind_norm, safe_name)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"历史文件不存在：{safe_name}")
    return file_response(raw, safe_name, media)


@router.get("/api/templates/download")
def download_template(name: str):
    """下载 templates/ 目录中的指定文件。"""
    filename = _safe_template_filename(name)
    path = templates_dir() / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"模板不存在：{filename}")
    data = path.read_bytes()
    lower = filename.lower()
    if lower.endswith(".csv"):
        media = "text/csv; charset=utf-8"
    elif lower.endswith(".xls"):
        media = "application/vnd.ms-excel"
    else:
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return file_response(data, filename, media)


@router.post("/api/templates/upload")
async def upload_template(file: UploadFile = File(...)):
    """上传模板到 templates/ 目录（同名覆盖）。"""
    filename = _safe_template_filename(file.filename or "upload.xlsx")
    if not filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls / .csv")
    data = await file.read()
    dest = templates_dir() / filename
    dest.write_bytes(data)
    return {"ok": True, "filename": filename, "files": list_user_templates()}


@router.get("/api/config/limits")
def get_limits():
    return {
        "weight_limit_kg": weight_limit_kg(),
        "throw_ratio": throw_ratio(),
        "input_columns": INPUT_COLUMNS,
    }


@router.put("/api/settings/deepseek-key")
def put_deepseek_key(body: dict):
    """Key 只在 Windows 上用 DPAPI 落盘。响应里没有原文。"""
    import sys

    from fba_tool.deepseek_secret import save_key

    if sys.platform != "win32":
        raise HTTPException(status_code=422, detail="非 Windows 环境不能保存 DeepSeek Key")
    key = str((body or {}).get("key") or "").strip()
    if not key:
        raise HTTPException(status_code=422, detail="Key 不能为空")
    save_key(key)
    return {"status": "已设置"}


@router.get("/api/settings/deepseek-key")
def get_deepseek_key():
    from fba_tool.deepseek_secret import status

    return {"status": status()}
