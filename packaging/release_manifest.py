"""S9-step5：安装包内容白名单（V3.2 起）。

PyInstaller spec 和测试都从这里取「哪些模板 / 出厂配置进安装包、从哪里取」：

* ``"repo"``    —— 直接用仓库里的原件（纯格式模板 / 不含真实数据的配置）。
* ``"release"`` —— 用 packaging/release_templates/ 下的 DEMO / 空白版（由
  packaging/build_release_templates.py 从原件生成）。原件留在 backend/ 里给测试和 golden 用。

不在白名单里的文件一律不打包（真实发货单、发票、箱唛、产品信息表、本机会话、领星密钥、发票历史等）。
兼容 Python 3.9。
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

REPO = "repo"
RELEASE = "release"

# 相对 backend/templates/ 的路径（用 / 分隔）
TEMPLATE_WHITELIST: Dict[str, str] = {
    "README.txt": REPO,
    "内部留档表.xlsx": REPO,
    "箱规导入模板.xlsx": REPO,
    "产品信息表_示例.csv": REPO,
    "customs/报关资料模板.xlsx": RELEASE,
    "forwarders/jiufang.xlsx": REPO,
    "forwarders/qiluo.xlsx": REPO,
    "forwarders/qiluo_t5.xlsx": REPO,
    "forwarders/send.xlsx": REPO,
    "forwarders/qiluo_t6.xlsx": RELEASE,
    "forwarders/deshu_t3.xlsx": RELEASE,
}

# 相对 backend/config/ 的文件名
CONFIG_WHITELIST: Dict[str, str] = {
    "user_settings.default.json": REPO,
    "formulas.default.json": REPO,
    "forwarders.default.json": RELEASE,
    "forwarder_mapping.default.json": REPO,
    "invoice_export_forwarders.default.json": REPO,
    "invoice_mapping.default.json": REPO,
    "fba_warehouse_corrections.json": REPO,
    "lingxing_field_map.json": REPO,
    "ticket_import_map.json": REPO,
    "amazon_sku_metadata.default.json": RELEASE,
    "fnsku_mapping.default.json": RELEASE,
    "sku_mapping.default.json": RELEASE,
    "exporter_profiles.default.json": RELEASE,
    "invoice_template_map.json": RELEASE,
}

RELEASE_SUBDIR = "release_templates"

# Marco 2026-10-20 决定：这 3 份真实数据模板原样留在仓库，不打进安装包。
# 文本扫描不解包它们；新增的其它真实二进制由 test_manifest_excludes_real_data_files 拦截。
ALLOWED_REAL_TEMPLATES_DECISION_DATE = "2026-10-20"
ALLOWED_REAL_TEMPLATES = (
    "发货录入样表.xlsx",
    "工厂表.xlsx",
    "货代表.xlsx",
)
# 空白官方 STA 表，不是上述 3 份已填写的真实数据模板，也不进安装包白名单。
KNOWN_BLANK_TEMPLATES = (
    "Send to Amazon表格.xlsx",
)


def _root(root: Path = None) -> Path:
    return Path(root).resolve() if root is not None else Path(__file__).resolve().parent.parent


def release_dir(root: Path = None) -> Path:
    return _root(root) / "packaging" / RELEASE_SUBDIR


def source_path(kind: str, rel: str, root: Path = None) -> Path:
    """kind = "templates" / "config"；返回这个白名单条目实际打包用的源文件。"""
    table = TEMPLATE_WHITELIST if kind == "templates" else CONFIG_WHITELIST
    origin = table[rel]
    base = (_root(root) / "backend" / kind) if origin == REPO else (release_dir(root) / kind)
    return base / Path(rel)


def entries(root: Path = None) -> List[Tuple[Path, str]]:
    """[(源文件, 包内相对路径 如 templates/forwarders/qiluo.xlsx)]"""
    out: List[Tuple[Path, str]] = []
    for kind, table in (("config", CONFIG_WHITELIST), ("templates", TEMPLATE_WHITELIST)):
        for rel in sorted(table):
            out.append((source_path(kind, rel, root), "%s/%s" % (kind, rel)))
    return out


def pyinstaller_datas(root: Path = None) -> List[Tuple[str, str]]:
    """spec 用：[(源文件, 包内目录)]。缺文件直接报错，免得悄悄打出一个缺模板的包。"""
    missing = [str(src) for src, _ in entries(root) if not src.is_file()]
    if missing:
        raise FileNotFoundError("白名单文件缺失：%s" % "; ".join(missing))
    return [(str(src), str(Path(dest).parent).replace("\\", "/")) for src, dest in entries(root)]


FORBIDDEN_REAL_NAMES = ("lingxing_listing_prices.xlsx",)
# 真实领星在售导出不得进仓库。合成用例只用内存里的 xlsx，不落这个文件名。
FORBIDDEN_REAL_GLOBS = ("*listing*.xlsx",)


def forbidden_real_hits(root: Path = None) -> List[str]:
    base = _root(root)
    skip = {"node_modules", ".git", "dist", ".venv", "__pycache__"}
    hits: List[str] = []
    for path in base.rglob("*"):
        if any(part in skip for part in path.parts):
            continue
        if not path.is_file():
            continue
        name = path.name.lower()
        if name in FORBIDDEN_REAL_NAMES or ("listing" in name and name.endswith(".xlsx")):
            hits.append(str(path.relative_to(base)))
    return hits
