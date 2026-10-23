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
    # 首次启动会在 import 时读 policy.json。bundled_default 只认 policy.default.json，
    # 缺了就落到不存在的 policy.json，便携版启动即 FileNotFoundError。
    # 品类、箱规渠道、商品分段、STA 下拉是装箱和发货预检要用的出厂规则，不是客户数据。
    # invoice_history.default.json 含业务参考，不进白名单。
    "policy.default.json": REPO,
    "category_map.default.json": REPO,
    "item_size_policy.default.json": REPO,
    "forwarder_registry.default.json": REPO,
    "sta_dropdowns.default.json": REPO,
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


def bundle_relpaths(root: Path = None) -> List[str]:
    """包内相对路径，一律正斜杠，例如 templates/forwarders/qiluo.xlsx。"""
    return [dest.replace("\\", "/") for _src, dest in entries(root)]


def _datas_dest_dir(bundle_rel: str) -> str:
    """PyInstaller datas 的第二项是目标目录，文件名由它自己接上。"""
    parent = Path(bundle_rel).parent.as_posix()
    return "." if parent in ("", ".") else parent


def pyinstaller_datas(root: Path = None) -> List[Tuple[str, str]]:
    """spec 用：[(源文件, 包内目录)]。缺文件或两条白名单挤到同一路径时直接报错。

    每个白名单文件单独一条，不要把 backend/templates 整目录塞进去。
    PyInstaller 会把源文件名接到目录后面，得到 bundle_relpaths() 里的路径。
    spec 在 Analysis 之后调用 assert_collected。finish_portable_dist 只验收
    _internal 里的这些文件，缺了就失败，不在那里补拷贝。
    """
    missing: List[str] = []
    seen = set()
    out: List[Tuple[str, str]] = []
    for src, dest in entries(root):
        if not src.is_file():
            missing.append(str(src))
            continue
        bundle = dest.replace("\\", "/")
        dest_dir = _datas_dest_dir(bundle)
        rebuilt = src.name if dest_dir == "." else "%s/%s" % (dest_dir, src.name)
        if rebuilt != bundle:
            raise ValueError("白名单路径和文件名不一致：%s / %s" % (bundle, rebuilt))
        if bundle in seen:
            raise ValueError("包内路径冲突，PyInstaller 只会留下一个：%s" % bundle)
        seen.add(bundle)
        out.append((str(src), dest_dir))
    if missing:
        raise FileNotFoundError("白名单文件缺失：%s" % "; ".join(missing))
    return out


def missing_collected(datas, root: Path = None) -> List[str]:
    """datas 条目是 (包内路径, ...) 。路径里的反斜杠按 Windows 打包结果归一成正斜杠。"""
    got = {str(entry[0]).replace("\\", "/") for entry in datas}
    return [rel for rel in bundle_relpaths(root) if rel not in got]


def assert_collected(datas, root: Path = None) -> None:
    """白名单文件必须已经在 Analysis.datas 里。缺了就停，不要事后拷进 _internal。"""
    missing = missing_collected(datas, root)
    if missing:
        raise SystemExit(
            "白名单文件没有进入 PyInstaller datas，不要在 finish_portable_dist 里补拷贝：%s"
            % "; ".join(missing)
        )


FORBIDDEN_REAL_NAMES = ("lingxing_listing_prices.xlsx",)
# 文件名带 listing 的 xlsx 视为真实领星在售导出，不得进仓库。
# 合成夹具用别的文件名（backend/tests/fixtures/synthetic/）。
# 本机私有导出用环境变量 FBA_LINGXING_OWNER_XLSX，不要把文件放进仓库。
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
        rel = path.relative_to(base).as_posix()
        name = path.name.lower()
        if name in FORBIDDEN_REAL_NAMES or ("listing" in name and name.endswith(".xlsx")):
            hits.append(rel)
    return hits
