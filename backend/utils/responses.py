"""HTTP 文件响应工具：附件下载、xlsx 流式响应。"""
from __future__ import annotations

import io
from urllib.parse import quote

from fastapi.responses import StreamingResponse

from settings import XLSX_MEDIA_TYPE


def attachment_disposition(filename: str) -> str:
    """RFC 5987：支持中文等非 ASCII 文件名的 Content-Disposition。"""
    ascii_fallback = "".join(ch if ord(ch) < 128 and ch not in ('"', "\\") else "_" for ch in filename)
    if not ascii_fallback.strip("."):
        ascii_fallback = "download"
    encoded = quote(filename, safe="")
    return f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


def file_response(data: bytes, filename: str, media_type: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": attachment_disposition(filename)},
    )


def xlsx_response(data: bytes, filename: str) -> StreamingResponse:
    return file_response(data, filename, XLSX_MEDIA_TYPE)


def pdf_response(data: bytes, filename: str) -> StreamingResponse:
    return file_response(data, filename, "application/pdf")
