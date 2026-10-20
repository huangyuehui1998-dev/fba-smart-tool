"""Step 4 历史测试文件：扫描 templates / history 目录，供前端快速选取。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal

from fba_tool.template_loader import app_root, templates_dir

FileKind = Literal["csv", "pdf"]

# 开发阶段无真实文件时的占位列表（与前端 Mock 对齐，便于联调）
_FALLBACK_CSV = [
    {"id": "mock-csv-a", "name": "测试装箱单_A.csv", "size_bytes": 12840, "source": "mock"},
    {"id": "mock-csv-b", "name": "测试装箱单_B.csv", "size_bytes": 9560, "source": "mock"},
    {"id": "mock-csv-c", "name": "亚马逊FBA表1.csv", "size_bytes": 11200, "source": "mock"},
]
_FALLBACK_PDF = [
    {"id": "mock-pdf-a", "name": "箱唛_FWA4.pdf", "size_bytes": 245760, "source": "mock"},
    {"id": "mock-pdf-b", "name": "箱唛_ORF2.pdf", "size_bytes": 198400, "source": "mock"},
    {"id": "mock-pdf-c", "name": "箱唛_GYR2.pdf", "size_bytes": 210880, "source": "mock"},
]

_MOCK_BYTES: Dict[str, bytes] = {
    "测试装箱单_A.csv": b"SKU,Title,Quantity\nTEST-SKU-1,Sample,10\n",
    "测试装箱单_B.csv": b"SKU,Title,Quantity\nTEST-SKU-2,Sample,20\n",
    "亚马逊FBA表1.csv": b"SKU,Title,Quantity\nTEST-SKU-3,Sample,15\n",
    "亚马逊FBA表.csv": b"SKU,Title,Quantity\nTEST-SKU-3,Sample,15\n",
    "箱唛_FWA4.pdf": b"%PDF-1.4 mock FWA4 label\n",
    "箱唛_ORF2.pdf": b"%PDF-1.4 mock ORF2 label\n",
    "箱唛_GYR2.pdf": b"%PDF-1.4 mock GYR2 label\n",
}


def history_dir() -> Path:
    root = app_root() / "history"
    (root / "csv").mkdir(parents=True, exist_ok=True)
    (root / "pdf").mkdir(parents=True, exist_ok=True)
    return root


def _is_step4_history_csv(name: str) -> bool:
    """排除产品信息表等非装箱单 CSV，避免误选导致校验异常。"""
    if "产品信息" in name:
        return False
    if name.startswith("~$"):
        return False
    return True


def _scan_dir(folder: Path, suffix: str, source: str, *, csv_packing_only: bool = False) -> List[Dict[str, Any]]:
    if not folder.exists():
        return []
    items: List[Dict[str, Any]] = []
    for path in sorted(folder.glob(f"*{suffix}")):
        if not path.is_file():
            continue
        if csv_packing_only and suffix == ".csv" and not _is_step4_history_csv(path.name):
            continue
        items.append(
            {
                "id": f"{source}:{path.name}",
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "source": source,
            }
        )
    return items


def list_history_files() -> Dict[str, List[Dict[str, Any]]]:
    """列出可选历史 CSV / PDF；目录为空时返回占位 Mock。"""
    hist = history_dir()
    csv_items = _scan_dir(hist / "csv", ".csv", "history", csv_packing_only=True) + _scan_dir(
        templates_dir(), ".csv", "templates", csv_packing_only=True
    )
    pdf_items = _scan_dir(hist / "pdf", ".pdf", "history") + _scan_dir(templates_dir(), ".pdf", "templates")

    seen_csv: set[str] = set()
    csv_unique: List[Dict[str, Any]] = []
    for item in csv_items:
        if item["name"] in seen_csv:
            continue
        seen_csv.add(item["name"])
        csv_unique.append(item)

    seen_pdf: set[str] = set()
    pdf_unique: List[Dict[str, Any]] = []
    for item in pdf_items:
        if item["name"] in seen_pdf:
            continue
        seen_pdf.add(item["name"])
        pdf_unique.append(item)

    if not csv_unique:
        csv_unique = list(_FALLBACK_CSV)
    if not pdf_unique:
        pdf_unique = list(_FALLBACK_PDF)

    return {"csv": csv_unique, "pdf": pdf_unique}


def resolve_history_file(kind: FileKind, name: str) -> Path | None:
    """按 kind + 文件名解析磁盘路径（禁止路径穿越）。"""
    safe_name = Path(name).name
    if safe_name != name or not safe_name:
        return None

    candidates: List[Path] = []
    hist = history_dir()
    if kind == "csv":
        candidates = [hist / "csv" / safe_name, templates_dir() / safe_name]
    elif kind == "pdf":
        candidates = [hist / "pdf" / safe_name, templates_dir() / safe_name]
    else:
        return None

    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def read_history_file_bytes(kind: str, name: str) -> bytes | None:
    path = resolve_history_file(kind, name)
    if path:
        return path.read_bytes()
    safe_name = Path(name).name
    return _MOCK_BYTES.get(safe_name)
