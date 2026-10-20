"""仓库文本扫描：拦新的真实货件号 / FNSKU / 报关单号 / 九方单号 / 手机号。

只扫 git ls-files 里的文本扩展名。xlsx/pdf 等二进制不解包。
docs/ 下政策出处 URL 里的命中不算。main@11c05d2 已经带有历史样本标识，
指纹基线只记录哈希和次数，不把原值再写进仓库。
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from collections import Counter
from pathlib import Path

# 基线文件只存哈希。不扫它，避免哈希里的数字串被手机号正则误伤，也避免基线自我包含。
SKIP_RELS = {
    "backend/tests/fixtures/synthetic/realdata_text_baseline.txt",
}

TEXT_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".json", ".md", ".txt", ".csv", ".yml", ".toml", ".html",
}

PATTERNS = (
    ("fnsku", re.compile(r"\bX00(?!TEST)[0-9A-Z]{7}\b")),
    ("shipment", re.compile(r"\bFBA1[0-9A-Z]{8,9}\b")),
    ("customs", re.compile(r"\bJUS\d{2}DD\d+")),
    ("jiufang", re.compile(r"\bLCL\d{4}[0-9A-Z]{4,}")),
    ("phone", re.compile(r"\b1[3-9]\d{9}\b")),
)

_URL_RE = re.compile(r"https?://[^\s)>\"]+")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


# 干净导出没有 .git。遍历时跳过依赖目录，避免把安装产物当成仓库文本。
WALK_SKIP_DIRS = {"node_modules", "dist", ".venv", "__pycache__", ".git"}


def _keep_text_rel(rel: str) -> bool:
    if rel in SKIP_RELS:
        return False
    parts = Path(rel).parts
    if any(part in WALK_SKIP_DIRS for part in parts):
        return False
    return Path(rel).suffix.lower() in TEXT_EXTS


def _git_available(root: Path) -> bool:
    try:
        subprocess.check_output(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return False


def walk_text_files(root: Path) -> list[str]:
    """没有 .git 时的文件清单。扩展名与 git 模式相同。"""
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if _keep_text_rel(rel):
            files.append(rel)
    return sorted(files)


def git_text_files(root: Path | None = None) -> list[str]:
    root = root or repo_root()
    if not _git_available(root):
        return walk_text_files(root)
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    files: list[str] = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", "surrogateescape")
        if _keep_text_rel(rel):
            files.append(rel)
    return files


def _in_docs_policy_url(rel: str, text: str, start: int, end: int) -> bool:
    if not rel.startswith("docs/"):
        return False
    for match in _URL_RE.finditer(text):
        if match.start() <= start and end <= match.end():
            return True
    return False


def scan_text(rel: str, text: str) -> list[tuple[str, str, int, str]]:
    """返回 (相对路径, 种类, 行号, 命中值)。政策 URL 已剔除。"""
    hits: list[tuple[str, str, int, str]] = []
    for kind, pattern in PATTERNS:
        for match in pattern.finditer(text):
            if _in_docs_policy_url(rel, text, match.start(), match.end()):
                continue
            line = text.count("\n", 0, match.start()) + 1
            hits.append((rel, kind, line, match.group()))
    return hits


def fingerprint(rel: str, kind: str, value: str) -> str:
    return hashlib.sha256(f"{rel}\0{kind}\0{value}".encode("utf-8")).hexdigest()


def scan_files(root: Path, rels: list[str]) -> Counter:
    counts: Counter = Counter()
    for rel in rels:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for rel_hit, kind, _line, value in scan_text(rel, text):
            counts[fingerprint(rel_hit, kind, value)] += 1
    return counts


def load_baseline(path: Path) -> Counter:
    counts: Counter = Counter()
    if not path.is_file():
        return counts
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, count = line.partition(" ")
        counts[digest] = int(count or "1")
    return counts


def format_baseline(counts: Counter) -> str:
    lines = ["# sha256(path\\0kind\\0value) count — 不含命中原值"]
    for digest in sorted(counts):
        lines.append(f"{digest} {counts[digest]}")
    lines.append("")
    return "\n".join(lines)
