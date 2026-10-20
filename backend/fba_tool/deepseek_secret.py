"""DeepSeek API key 只存在本机 DPAPI 密文里，接口不回传原文。"""
from __future__ import annotations

import sys
from pathlib import Path

from fba_tool.app_paths import app_data_dir


def secret_path() -> Path:
    return app_data_dir() / "secrets" / "deepseek_key.bin"


def status() -> str:
    path = secret_path()
    if path.is_file() and path.stat().st_size > 0:
        return "已设置"
    return "未设置"


def save_key(key: str) -> None:
    if sys.platform != "win32":
        raise OSError("非 Windows 环境不能保存 DeepSeek Key")
    blob = _dpapi_protect(key.encode("utf-8"))
    path = secret_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)


def load_key() -> str:
    """只给服务端调用。GET 接口不得调用本函数。"""
    if sys.platform != "win32":
        return ""
    path = secret_path()
    if not path.is_file():
        return ""
    return _dpapi_unprotect(path.read_bytes()).decode("utf-8")


def _dpapi_protect(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("DPAPI 加密失败")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buf = ctypes.create_string_buffer(data)
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    ):
        raise OSError("DPAPI 解密失败")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
