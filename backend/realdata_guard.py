"""S9-step4-fix3 测试护栏：临时 app_data / tmp_path 里不许出现真实库、真实会话的副本（按内容比对）。

做法：
- 会话开始时对真实来源（仓库 backend/fba_master.db、backend/config/sessions/**、仓库根 config/sessions/**、
  仓库根 app_data/ 下的 fba_master.db 和 sessions/**）算 SHA-256，只放在内存里，不输出、不落盘；
- 扫描临时目录里的全部文件：先按大小粗筛，大小和某个真实来源相同才算哈希；
- SQLite 文件（文件头 "SQLite format 3\\0"）另按表特征认：真实库 product_master 每行 (sku, updated_at) 的指纹集合
  （同样只在内存里）。测试自己建的库，行是测试写的、updated_at 是运行时生成的，不会命中；
  真实库被复制后又被 init 改写（加列、补字段、改大小 / mtime）也认得出来；
- 已检查过、没变（路径 + 大小 + mtime 不变）的文件不再重复读，保证全量测试不明显变慢。
输出只有临时目录里的相对路径和类型，不含真实来源的路径、哈希或内容。
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote
from typing import Dict, Iterable, List, Optional, Set, Tuple

SQLITE_MAGIC = b"SQLite format 3\x00"
_CHUNK = 1 << 20


def real_sources(backend_dir: Path, project_root: Path, extra_app_data: Iterable[Path] = ()) -> List[Path]:
    """可能是真实数据的来源文件。"""
    out: List[Path] = []
    roots = [Path(backend_dir), Path(project_root), Path(project_root) / "app_data", *[Path(p) for p in extra_app_data]]
    seen: Set[str] = set()
    for root in roots:
        db = root / "fba_master.db"
        if db.is_file() and str(db.resolve()) not in seen:
            seen.add(str(db.resolve()))
            out.append(db)
    for sess in [Path(backend_dir) / "config" / "sessions", Path(project_root) / "config" / "sessions",
                 *[r / "sessions" for r in roots[2:]]]:
        if sess.is_dir():
            for p in sess.rglob("*"):
                if p.is_file() and str(p.resolve()) not in seen:
                    seen.add(str(p.resolve()))
                    out.append(p)
    return out


def _sha256(path: Path) -> Optional[bytes]:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(_CHUNK), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.digest()


def _is_sqlite(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(16) == SQLITE_MAGIC
    except OSError:
        return False


def _row_prints(path: Path) -> Set[bytes]:
    """SQLite 表特征：product_master 每行 (sku, updated_at) 的指纹。只读打开（immutable），不改文件。"""
    uri = "file:" + quote(Path(path).resolve().as_posix(), safe="/:") + "?mode=ro&immutable=1"
    try:
        con = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return set()
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(product_master)")}
        if "sku" not in cols:
            return set()
        stamp = "updated_at" if "updated_at" in cols else "NULL"
        rows = con.execute(f"SELECT sku, {stamp} FROM product_master")
        return {hashlib.sha256(f"{s}\x1f{u}".encode("utf-8", "replace")).digest() for s, u in rows}
    except sqlite3.Error:
        return set()
    finally:
        con.close()


class RealDataIndex:
    """真实来源的内容指纹（只在内存里）。"""

    def __init__(self, sources: Iterable[Path]):
        self.by_size: Dict[int, Set[bytes]] = {}
        self.kind_by_digest: Dict[bytes, str] = {}
        self.row_prints: Set[bytes] = set()
        self.count = 0
        for p in sources:
            p = Path(p)
            try:
                size = p.stat().st_size
            except OSError:
                continue
            dig = _sha256(p)
            if dig is None:
                continue
            self.count += 1
            self.by_size.setdefault(size, set()).add(dig)
            sqlite_file = _is_sqlite(p)
            self.kind_by_digest[dig] = "真实库" if sqlite_file else "真实会话"
            if sqlite_file:
                self.row_prints |= _row_prints(p)
        self._cache: Dict[str, Tuple[int, int, str]] = {}

    def _check_file(self, p: Path) -> str:
        try:
            st = p.stat()
        except OSError:
            return ""
        key = str(p)
        hit = self._cache.get(key)
        if hit and hit[0] == st.st_size and hit[1] == st.st_mtime_ns:
            return hit[2]
        why = ""
        digests = self.by_size.get(st.st_size)
        if digests:
            dig = _sha256(p)
            if dig is not None and dig in digests:
                why = f"内容与{self.kind_by_digest.get(dig, '真实来源')}一致（SHA-256）"
        if not why and self.row_prints and st.st_size >= 512 and _is_sqlite(p):
            n = len(_row_prints(p) & self.row_prints)
            if n:
                why = f"SQLite 库里有 {n} 行与真实库 product_master 的行相同（sku + updated_at）"
        self._cache[key] = (st.st_size, st.st_mtime_ns, why)
        return why

    def find_copies(self, root: Path) -> List[str]:
        """返回 root 下疑似真实副本的说明（相对路径 + 原因），为空表示干净。"""
        root = Path(root)
        if not root.is_dir() or not self.count:
            return []
        problems: List[str] = []
        for dp, _dn, fns in os.walk(root):
            for fn in fns:
                p = Path(dp) / fn
                why = self._check_file(p)
                if why:
                    problems.append(f"{p.relative_to(root).as_posix()}: {why}")
        return sorted(problems)


def find_real_copies(app_data: Path, sources: Iterable[Path]) -> List[str]:
    """一次性检查（不复用缓存）。"""
    return RealDataIndex(sources).find_copies(Path(app_data))
