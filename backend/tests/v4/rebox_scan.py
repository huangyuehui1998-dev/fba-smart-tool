"""命名 FBA 批量扫描要跳过的刷箱 / FIST / golden / 待分配路径。

第 13/14 批命名货件扫描只用装箱明细和 SEND 箱单。
刷箱、FIST、golden samples，以及文件名里的「待分配」，不是那两批的命名入库。
这里只提供路径判断，不改 Step4 命名货件 CSV+PDF 入库。
"""
from __future__ import annotations

from pathlib import Path


def relative_parts(path: Path, root: Path) -> tuple[str, ...]:
    try:
        return path.relative_to(root).parts
    except ValueError:
        return path.parts


def is_fist_part(folded: str) -> bool:
    """目录名或文件名是 FIST。不把别的词里夹着的 fist 算进去。"""
    if folded == "fist":
        return True
    stem, dot, _ext = folded.rpartition(".")
    if dot and stem == "fist":
        return True
    return folded.startswith("fist") and len(folded) > 4 and not folded[4].isalnum()


def rebox_or_fist_path(path: Path, root: Path) -> bool:
    """刷箱、FIST、golden samples，以及文件名里的「待分配」，不是第 13/14 批命名货件。"""
    if "待分配" in path.name:
        return True
    rel_parts = relative_parts(path, root)
    folded_parts = [part.strip().casefold() for part in rel_parts]
    for part, folded in zip(rel_parts, folded_parts):
        text = part.strip()
        if "刷箱" in text or is_fist_part(folded):
            return True
        if "golden" in folded and "sample" in folded:
            return True
        if folded == "golden":
            return True
    for left, right in zip(folded_parts, folded_parts[1:]):
        if "golden" in left and "sample" in right:
            return True
    return False


def packing_or_send_boxlist(path: Path, root: Path) -> bool:
    """只留装箱明细，以及 SEND 的箱单。刷箱里的 SEND 不是这种箱单。"""
    text = str(Path(*relative_parts(path, root)))
    if "装箱明细" in text:
        return True
    return "箱单" in text and "send" in text.casefold()


def batch_csvs(root: Path) -> dict[str, list[Path]]:
    found = {"13": [], "14": []}
    for path in root.rglob("*.csv"):
        if path.name.startswith("~$") or rebox_or_fist_path(path, root) or not packing_or_send_boxlist(path, root):
            continue
        text = str(path).replace("\\", "/")
        if "第13批" in text or "/13/" in text:
            found["13"].append(path)
        elif "第14批" in text or "/14/" in text:
            found["14"].append(path)
    return found


def invoice_files(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*"):
        if not path.is_file() or path.name.startswith("~$") or rebox_or_fist_path(path, root):
            continue
        if path.suffix.lower() not in {".xlsx", ".xlsm"}:
            continue
        name = path.name.lower()
        if any(token in path.name for token in ("发票", "箱单", "Invoice", "invoice")):
            found.append(path)
        elif "send" in name and "amazon" not in name:
            found.append(path)
    return found


# test_v4_ops_r3 继续用原来的名字。
_relative_parts = relative_parts
_is_fist_part = is_fist_part
_rebox_or_fist_path = rebox_or_fist_path
_packing_or_send_boxlist = packing_or_send_boxlist
_batch_csvs = batch_csvs
_invoice_files = invoice_files
