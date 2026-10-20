"""全局测试隔离：把 app_data 指到临时目录，跑测试不读写真实 app_data（数据库、配置、会话）。"""
import os
import sys
import tempfile
from pathlib import Path

# TD-5：用例按模块放在 tests/<模块>/。互相 import test_* 时仍按文件名找得到。
_BACKEND = Path(__file__).resolve().parent
for _dir in (_BACKEND / "tests").rglob("*"):
    if _dir.is_dir() and any(_dir.glob("test_*.py")):
        _entry = str(_dir)
        if _entry not in sys.path:
            sys.path.insert(0, _entry)

_TMP_APP_DATA = tempfile.mkdtemp(prefix="fba_test_app_data_")
os.environ["FBA_APP_DATA_DIR"] = _TMP_APP_DATA
os.environ.pop("FBA_ACCESS_TOKEN", None)

import pytest


@pytest.fixture(scope="session", autouse=True)
def _init_global_temp_app_data():
    """S8-fix3 N7：会话开始时在全局临时 app_data 里建好目录和全部表。
    main.py 在导入时 create_app() 建表；若第一次导入 main 发生在某个把库指到 tmp_path 的测试里（如 test_s8fix1_dec12_e2e），
    表只会建在那个临时库，之后用全局临时库的测试会报 no such table。这里只影响测试，不改产品行为。"""
    from fba_tool.app_paths import ensure_app_data_layout
    from fba_tool.master_db import init_master_db

    ensure_app_data_layout()
    _assert_no_real_copies(_TMP_APP_DATA, "会话初始化")
    init_master_db()
    yield


def _real_sources():
    from pathlib import Path

    from realdata_guard import real_sources

    backend = Path(__file__).resolve().parent
    return real_sources(backend, backend.parent)


_REAL_INDEX = None


def _real_index():
    """真实来源的 SHA-256 和 SQLite 表特征：会话里只算一次，只放内存，不输出、不落盘。"""
    global _REAL_INDEX
    if _REAL_INDEX is None:
        from realdata_guard import RealDataIndex

        _REAL_INDEX = RealDataIndex(_real_sources())
    return _REAL_INDEX


def _assert_no_real_copies(app_data, where):
    """S9-step4-fix3 护栏：临时目录里不许有真实 fba_master.db / sessions 的副本（按内容比对：大小粗筛 + SHA-256 +
    SQLite 表特征；改名、不保留 mtime、放到别的目录、被 init 改写过都认得出来）。"""
    problems = _real_index().find_copies(app_data)
    assert not problems, f"{where}：临时目录（{app_data}）里发现真实数据副本：{problems}"


@pytest.fixture(autouse=True)
def _guard_no_real_data_copies(request):
    """每个测试结束后检查全局临时 app_data，以及该测试用到的 tmp_path。"""
    yield
    _assert_no_real_copies(_TMP_APP_DATA, request.node.nodeid)
    tmp = request.node.funcargs.get("tmp_path") if hasattr(request.node, "funcargs") else None
    if tmp is not None:
        _assert_no_real_copies(tmp, request.node.nodeid + " (tmp_path)")


def pytest_configure(config):
    config.addinivalue_line("markers", "acceptance: 验收脚本复现项，默认不进门禁（pytest -m acceptance）")


def pytest_collection_modifyitems(config, items):
    """acceptance 默认不收集。显式 -m acceptance 时保留。"""
    markexpr = getattr(config.option, "markexpr", "") or ""
    if "acceptance" in markexpr:
        return
    items[:] = [item for item in items if "acceptance" not in item.keywords]


def pytest_sessionfinish(session, exitstatus):
    """会话结束：再查全局临时 app_data 和本次 pytest 的全部 tmp_path；发现副本就让整次测试失败。"""
    roots = [_TMP_APP_DATA]
    try:
        roots.append(str(session.config._tmp_path_factory.getbasetemp()))
    except Exception:  # noqa: BLE001
        pass
    found = []
    for root in roots:
        found += [f"{root}: {p}" for p in _real_index().find_copies(root)]
    if found:
        print(f"\n[真实数据护栏] 临时目录里发现真实数据副本：{found}")
        session.exitstatus = 1
