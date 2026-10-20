"""提交前扫描：文本文件里的真实货件号 / FNSKU / 报关单号 / 九方单号 / 手机号。

main@11c05d2 的测试和出厂配置里已经有历史样本标识。严格清空会拆掉 golden 断言，
所以门禁比对的是指纹基线（只存哈希）。新命中（例如 backend/foo.txt）会失败。
docs/ 里政策出处 URL 中的命中不算。二进制不解包。
"""
from __future__ import annotations

from pathlib import Path

import pytest

import importlib.util
import sys

from tests.realdata_scan import format_baseline, git_text_files, load_baseline, repo_root, scan_files, scan_text

ROOT = repo_root()
BASELINE = ROOT / "backend" / "tests" / "fixtures" / "synthetic" / "realdata_text_baseline.txt"
_REAL_SHIPMENT = "FBA1" + "9ABCDEFGH"


def _manifest():
    path = ROOT / "packaging" / "release_manifest.py"
    spec = importlib.util.spec_from_file_location("release_manifest_scan", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["release_manifest_scan"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_whitelist_templates_exist_and_text_scan_matches_baseline():
    manifest = _manifest()
    assert manifest.ALLOWED_REAL_TEMPLATES_DECISION_DATE == "2026-10-20"
    for name in manifest.ALLOWED_REAL_TEMPLATES:
        assert (ROOT / "backend" / "templates" / name).is_file(), name
    current = scan_files(ROOT, git_text_files(ROOT))
    expected = load_baseline(BASELINE)
    if current != expected:
        extra = current - expected
        missing = expected - current
        pytest.fail(
            "文本扫描指纹与基线不一致。\n"
            f"新增 {len(extra)} 条、消失 {len(missing)} 条。\n"
            "若是有意改动历史样本标识，重新生成 "
            "backend/tests/fixtures/synthetic/realdata_text_baseline.txt；"
            "新的真实货件号 / FNSKU 不允许进入仓库。\n"
            + format_baseline(current)
        )


def test_new_shipment_id_in_backend_foo_txt_fails_scan(tmp_path):
    target = ROOT / "backend" / "foo.txt"
    assert not target.exists()
    text = f"货件 {_REAL_SHIPMENT}\n"
    target.write_text(text, encoding="utf-8")
    try:
        hits = scan_text("backend/foo.txt", text)
        assert hits, "含 FBA1 真实格式货件号的文本必须被扫描命中"
        listed = git_text_files(ROOT) + ["backend/foo.txt"]
        current = scan_files(ROOT, listed)
        baseline = load_baseline(BASELINE)
        assert current != baseline
    finally:
        target.unlink(missing_ok=True)


def test_docs_policy_url_is_whitelisted_and_plain_text_is_not():
    text = f"出处 https://example.com/policy/{_REAL_SHIPMENT}\n"
    assert scan_text("docs/policy.md", text) == []
    assert scan_text("backend/foo.txt", text)


def test_synthetic_ids_do_not_match():
    text = "FBATEST00001 X00TEST001 JUS-not-real 1380013800\n"
    # 1380013800 是 11 位，手机号正则要 1[3-9] + 9 位 = 11 位，13800138000 才是 11 位。
    assert scan_text("backend/tests/fixtures/synthetic/note.txt", text) == []
