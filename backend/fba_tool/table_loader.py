"""全格式表格智能路由：任意主流表格 → 统一原始 DataFrame（header=None, dtype=str）。

职责边界：
- 本模块只做格式识别与字节 → 网格转换
- 业务逻辑（SKU 行扫描、正则列映射、跳过商标 Sheet）留在各 Parser
"""
from __future__ import annotations

import io
from typing import Iterator, List, Tuple

import pandas as pd

# ZIP 容器（xlsx / xlsm 等）
_MAGIC_ZIP = b"PK"
# OLE 复合文档（xls / xlsb）
_MAGIC_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_EXCEL_ZIP_EXTS = frozenset({"xlsx", "xlsm"})
_EXCEL_OLE_EXTS = frozenset({"xls", "xlsb"})
_TEXT_EXTS = frozenset({"csv", "tsv", "txt"})
_ALL_EXTS = _EXCEL_ZIP_EXTS | _EXCEL_OLE_EXTS | _TEXT_EXTS

_READ_KW = {"header": None, "dtype": str, "keep_default_na": False}


def _file_ext(filename: str) -> str:
    name = (filename or "").strip().lower()
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[-1]


def detect_table_format(file_bytes: bytes, filename: str = "") -> str:
    """识别表格格式：后缀优先，文件魔数兜底。

    返回：xlsx | xlsm | xls | xlsb | csv | tsv | unknown
    """
    ext = _file_ext(filename)
    head = file_bytes[:8] if file_bytes else b""

    if head[:2] == _MAGIC_ZIP:
        if ext in _EXCEL_ZIP_EXTS:
            return ext
        return "xlsx"

    if head[:8] == _MAGIC_OLE:
        if ext == "xlsb":
            return "xlsb"
        if ext == "xls":
            return "xls"
        return "xls"

    if ext in _TEXT_EXTS:
        return ext
    if ext in _EXCEL_ZIP_EXTS:
        return ext
    if ext in _EXCEL_OLE_EXTS:
        return ext

    if _looks_like_text_table(file_bytes):
        return "csv"

    return "unknown"


def _looks_like_text_table(file_bytes: bytes) -> bool:
    if not file_bytes:
        return False
    sample = file_bytes[:4096]
    if b"\x00" in sample:
        return False
    for encoding in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            text = sample.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return False
    line = text.splitlines()[0] if text.splitlines() else ""
    if not line.strip():
        return False
    return any(sep in line for sep in (",", "\t", ";"))


def load_raw_table(file_bytes: bytes, filename: str = "") -> pd.DataFrame:
    """全格式路由 → 无表头原始网格（全 str）。

    Excel 仅返回第一个 Sheet 的原始表；多 Sheet 场景请用 ``iter_excel_sheet_frames``。
    """
    if not file_bytes:
        return pd.DataFrame()

    fmt = detect_table_format(file_bytes, filename)

    if fmt in _EXCEL_ZIP_EXTS or fmt == "xlsx":
        frames = list(iter_excel_sheet_frames(file_bytes, filename))
        if not frames:
            return pd.DataFrame()
        return frames[0][1]

    if fmt in _EXCEL_OLE_EXTS:
        frames = list(iter_excel_sheet_frames(file_bytes, filename))
        if not frames:
            return pd.DataFrame()
        return frames[0][1]

    if fmt in _TEXT_EXTS or fmt == "csv":
        return _load_text_raw_grid(file_bytes, fmt if fmt in _TEXT_EXTS else "csv")

    raise ValueError(
        f"暂不支持的文件格式（.{_file_ext(filename) or '未知'}）。"
        "请上传 Excel（xlsx/xlsm/xls/xlsb）或文本表（csv/tsv/txt）。"
    )


def iter_excel_sheet_frames(
    file_bytes: bytes,
    filename: str = "",
) -> Iterator[Tuple[str, pd.DataFrame]]:
    """遍历 Excel 各 Sheet，产出 (sheet_name, 原始网格 DataFrame)。"""
    if not file_bytes:
        return

    fmt = detect_table_format(file_bytes, filename)
    bio = io.BytesIO(file_bytes)

    if fmt in _EXCEL_ZIP_EXTS or fmt == "xlsx":
        engine = "openpyxl"
    elif fmt == "xlsb":
        engine = "pyxlsb"
    elif fmt == "xls":
        engine = "xlrd"
    else:
        if file_bytes[:2] == _MAGIC_ZIP:
            engine = "openpyxl"
        elif file_bytes[:8] == _MAGIC_OLE:
            engine = _excel_ole_engine(file_bytes, filename)
        else:
            return

    try:
        xl = pd.ExcelFile(bio, engine=engine)
    except Exception as exc:
        if engine == "xlrd" and file_bytes[:8] == _MAGIC_OLE:
            bio.seek(0)
            try:
                xl = pd.ExcelFile(io.BytesIO(file_bytes), engine="pyxlsb")
            except Exception:
                raise _wrap_read_error(exc, filename) from exc
        else:
            raise _wrap_read_error(exc, filename) from exc

    for sheet in xl.sheet_names:
        df = pd.read_excel(xl, sheet_name=sheet, **_READ_KW)
        yield sheet, df


def _excel_ole_engine(file_bytes: bytes, filename: str) -> str:
    ext = _file_ext(filename)
    if ext == "xlsb":
        return "pyxlsb"
    return "xlrd"


def _load_text_raw_grid(file_bytes: bytes, fmt: str) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
        try:
            text = file_bytes.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = file_bytes.decode("utf-8", errors="replace")

    if fmt == "tsv":
        seps: List[str] = ["\t"]
    elif fmt == "csv":
        seps = [",", "\t", ";"]
    else:
        first_line = text.splitlines()[0] if text.splitlines() else ""
        if first_line.count("\t") >= first_line.count(","):
            seps = ["\t", ",", ";"]
        else:
            seps = [",", "\t", ";"]

    for sep in seps:
        try:
            df = pd.read_csv(
                io.StringIO(text),
                sep=sep,
                engine="python",
                **_READ_KW,
            )
            if df.shape[1] > 1:
                return df
        except Exception:
            continue

    return pd.read_csv(
        io.StringIO(text),
        engine="python",
        **_READ_KW,
    )


def _wrap_read_error(exc: Exception, filename: str) -> ValueError:
    msg = str(exc).lower()
    if "password" in msg or "encrypted" in msg:
        return ValueError("文件已加密或受密码保护，请另存为未加密的 xlsx/csv 后重试。")
    if "corrupt" in msg or "damaged" in msg:
        return ValueError("文件已损坏或不是有效的表格文件，请重新导出后上传。")
    ext = _file_ext(filename)
    return ValueError(
        f"文件解析失败（.{ext or '未知'}），请检查是否加密、损坏或格式不匹配。详情：{exc}"
    )


def supported_upload_extensions() -> Tuple[str, ...]:
    """供 API / 文档引用的支持后缀列表。"""
    return tuple(sorted(_ALL_EXTS))
