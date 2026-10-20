"""密钥加密存储（方案 v8 §3.2）：Windows DPAPI（CryptProtectData，当前用户范围），不引入新依赖。

- protect / unprotect：明文 ⇄ "dpapi:v1:<base64>"；
- 非 Windows 且没有可用后端时 available() 为 False，保存密钥会报错（不会退回明文）；
- 测试里可用 set_backend() 换成假后端验证迁移逻辑；Windows 上另有真实 DPAPI 往返用例。
"""
from __future__ import annotations

import base64
import sys
from typing import Callable, Optional, Tuple

PREFIX = "dpapi:v1:"
_ENTROPY = b"FBA_Smart_Tool/lingxing"


class SecretStoreError(RuntimeError):
    pass


def _dpapi() -> Optional[Tuple[Callable[[bytes], bytes], Callable[[bytes], bytes]]]:
    if not sys.platform.startswith("win"):
        return None
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    CRYPTPROTECT_UI_FORBIDDEN = 0x01

    def _blob(data: bytes):
        buf = ctypes.create_string_buffer(data, len(data))
        return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    def _take(out: DATA_BLOB) -> bytes:
        try:
            return ctypes.string_at(out.pbData, out.cbData)
        finally:
            kernel32.LocalFree(out.pbData)

    def enc(data: bytes) -> bytes:
        src, _b1 = _blob(data)
        ent, _b2 = _blob(_ENTROPY)
        out = DATA_BLOB()
        if not crypt32.CryptProtectData(ctypes.byref(src), "FBA", ctypes.byref(ent), None, None,
                                        CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
            raise SecretStoreError("DPAPI 加密失败")
        return _take(out)

    def dec(data: bytes) -> bytes:
        src, _b1 = _blob(data)
        ent, _b2 = _blob(_ENTROPY)
        out = DATA_BLOB()
        if not crypt32.CryptUnprotectData(ctypes.byref(src), None, ctypes.byref(ent), None, None,
                                          CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out)):
            raise SecretStoreError("DPAPI 解密失败（密文可能来自别的 Windows 用户或电脑，请重新填写密钥）")
        return _take(out)

    return enc, dec


_backend = _dpapi()


def set_backend(backend: Optional[Tuple[Callable[[bytes], bytes], Callable[[bytes], bytes]]]) -> None:
    """测试用：替换加解密后端（None = 不可用）。"""
    global _backend
    _backend = backend


def available() -> bool:
    return _backend is not None


def is_protected(value: str) -> bool:
    return str(value or "").startswith(PREFIX)


def protect(plain: str) -> str:
    if _backend is None:
        raise SecretStoreError("本机不支持加密保存密钥（需要 Windows DPAPI），已拒绝以明文保存")
    return PREFIX + base64.b64encode(_backend[0](plain.encode("utf-8"))).decode("ascii")


def unprotect(token: str) -> str:
    if not is_protected(token):
        raise SecretStoreError("不是加密后的密钥")
    if _backend is None:
        raise SecretStoreError("本机不支持解密密钥（需要 Windows DPAPI）")
    return _backend[1](base64.b64decode(token[len(PREFIX):])).decode("utf-8")
