"""便携包：白名单进 PyInstaller datas，zip 保留中文名，CI 只上传 artifact。"""
from __future__ import annotations

import importlib.util
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
PACKAGING = ROOT / "packaging"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


M = _load("release_manifest_portable", PACKAGING / "release_manifest.py")
FIN = _load("finish_portable_dist_portable", ROOT / "scripts" / "finish_portable_dist.py")


def test_datas_cover_each_whitelist_file_once():
    entries = M.entries(ROOT)
    datas = M.pyinstaller_datas(ROOT)
    assert len(datas) == len(entries)
    rebuilt = []
    for src, dest_dir in datas:
        name = Path(src).name
        rebuilt.append(name if dest_dir == "." else f"{dest_dir}/{name}")
    assert rebuilt == [dest.replace("\\", "/") for _src, dest in entries]
    assert len(set(rebuilt)) == len(rebuilt)
    assert "templates/forwarders/qiluo.xlsx" in rebuilt
    assert "templates/工厂表.xlsx" not in rebuilt
    assert "config/lingxing.json" not in rebuilt
    assert "config/invoice_history.default.json" not in rebuilt


# 便携版 import placement_fee 就会 load_policy()。缺 policy.default.json 时
# bundled_default 回落到不存在的 policy.json，启动即 FileNotFoundError。
FACTORY_POLICY_DEFAULTS = (
    "policy.default.json",
    "category_map.default.json",
    "item_size_policy.default.json",
    "forwarder_registry.default.json",
    "sta_dropdowns.default.json",
)


def test_factory_policy_defaults_are_in_whitelist_and_datas():
    for name in FACTORY_POLICY_DEFAULTS:
        assert M.CONFIG_WHITELIST.get(name) == M.REPO, name
        assert (BACKEND / "config" / name).is_file(), name
    datas = M.pyinstaller_datas(ROOT)
    rebuilt = []
    for src, dest_dir in datas:
        name = Path(src).name
        rebuilt.append(name if dest_dir == "." else f"{dest_dir}/{name}")
    for name in FACTORY_POLICY_DEFAULTS:
        assert f"config/{name}" in rebuilt, name
        assert Path(next(src for src, dest in datas if Path(src).name == name)).is_file()
    assert "config/invoice_history.default.json" not in rebuilt
    assert "config/lingxing.json" not in rebuilt
    datas_win = [(rel.replace("/", "\\"), "DATA") for rel in M.bundle_relpaths(ROOT)]
    dropped = [
        item
        for item in datas_win
        if not str(item[0]).replace("\\", "/").endswith("config/policy.default.json")
    ]
    with pytest.raises(SystemExit, match="policy.default.json"):
        M.assert_collected(dropped, ROOT)


def test_assert_collected_accepts_windows_dests_and_rejects_gaps():
    datas = [(rel.replace("/", "\\"), "unused", "DATA") for rel in M.bundle_relpaths(ROOT)]
    M.assert_collected(datas, ROOT)
    dropped = [item for item in datas if not str(item[0]).replace("\\", "/").endswith("templates/forwarders/qiluo.xlsx")]
    with pytest.raises(SystemExit, match="qiluo.xlsx"):
        M.assert_collected(dropped, ROOT)


def test_spec_fails_closed_when_datas_are_missing():
    text = (PACKAGING / "FBA_Smart_Tool.spec").read_text(encoding="utf-8")
    assert "_assert_collected(a.datas, ROOT)" in text
    assert 'contents_directory="_internal"' in text
    assert "rglob" not in text
    assert '"templates")' not in text


def test_pyinstaller_pin_matches_dev_lock():
    pin = (PACKAGING / "requirements-pyinstaller.txt").read_text(encoding="utf-8")
    lock = (BACKEND / "requirements-dev.lock.txt").read_text(encoding="utf-8")
    ps1 = (ROOT / "scripts" / "build_standalone.ps1").read_text(encoding="utf-8-sig")
    for line in ("pyinstaller==6.20.0", "pyinstaller-hooks-contrib==2026.5"):
        assert line in pin and line in lock
    assert "requirements-pyinstaller.txt" in ps1
    assert "pip install pyinstaller --quiet" not in ps1


def test_missing_internal_names_qiluo_and_does_not_copy(tmp_path):
    missing = FIN.missing_internal_files(tmp_path)
    assert "_internal/templates/forwarders/qiluo.xlsx" in missing
    assert "_internal/dist/index.html" in missing
    assert not (tmp_path / "_internal").exists()
    text = (ROOT / "scripts" / "finish_portable_dist.py").read_text(encoding="utf-8")
    assert "不要手工拷" in text
    assert "missing_internal_files" in text


def test_utf8_zip_keeps_chinese_names_and_drops_user_data(tmp_path):
    out = tmp_path / "FBA_Smart_Tool"
    forwarders = out / "_internal" / "templates" / "forwarders"
    forwarders.mkdir(parents=True)
    (out / "_internal" / "config").mkdir()
    (out / "_internal" / "dist").mkdir()
    (out / "FBA_Smart_Tool.exe").write_bytes(b"MZ")
    (forwarders / "qiluo.xlsx").write_bytes(b"PK")
    (out / "_internal" / "config" / "forwarders.default.json").write_text("{}", encoding="utf-8")
    (out / "_internal" / "dist" / "index.html").write_text("<html>FBA Smart Tool</html>", encoding="utf-8")
    (out / "app_data").mkdir()
    (out / "app_data" / "lingxing.json").write_text("secret", encoding="utf-8")
    (out / "_internal" / "scipy" / "ndimage").mkdir(parents=True)
    (out / "_internal" / "scipy" / "ndimage" / "dots.db").write_bytes(b"not-ours")
    FIN._write_launcher(out)
    (out / FIN.README_NAME).write_text("使用说明", encoding="utf-8")

    zip_path = tmp_path / "FBA_Smart_Tool_V4_便携版.zip"
    FIN.write_utf8_zip(out, zip_path)
    required = [
        "FBA_Smart_Tool/FBA_Smart_Tool.exe",
        "FBA_Smart_Tool/启动FBA工具.bat",
        "FBA_Smart_Tool/使用说明.txt",
        "FBA_Smart_Tool/_internal/templates/forwarders/qiluo.xlsx",
        "FBA_Smart_Tool/_internal/config/forwarders.default.json",
        "FBA_Smart_Tool/_internal/dist/index.html",
    ]
    FIN.verify_portable_zip(zip_path, required)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert all("\\" not in name for name in names)
        assert not any("app_data" in name or name.endswith("lingxing.json") for name in names)
        # 第三方库里的 .db 不误伤；我们自己的配置树里的才拦截。
        assert "FBA_Smart_Tool/_internal/scipy/ndimage/dots.db" in names
        for name in ("FBA_Smart_Tool/启动FBA工具.bat", "FBA_Smart_Tool/使用说明.txt"):
            info = zf.getinfo(name)
            assert info.flag_bits & FIN.UTF8_NAME_FLAG
            assert info.filename == name
        launcher = zf.read("FBA_Smart_Tool/启动FBA工具.bat")
        assert launcher.startswith(b"@echo off")
        assert b"FBA_Smart_Tool.exe" in launcher

    assert FIN._forbidden_member("FBA_Smart_Tool/_internal/config/lingxing.json")
    assert FIN._forbidden_member("FBA_Smart_Tool/app_data/secret.txt")
    assert FIN._forbidden_member("FBA_Smart_Tool/_internal/config/sessions/a.json")
    assert not FIN._forbidden_member("FBA_Smart_Tool/_internal/scipy/ndimage/dots.db")

    secret = out / "_internal" / "config" / "lingxing.json"
    secret.write_text("nope", encoding="utf-8")
    bad_zip = tmp_path / "bad.zip"
    FIN.write_utf8_zip(out, bad_zip)
    with pytest.raises(SystemExit, match="禁止发布"):
        FIN.verify_portable_zip(bad_zip, required)


def test_windows_workflow_uploads_artifact_and_does_not_publish():
    text = (ROOT / ".github" / "workflows" / "portable-windows.yml").read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in text
    assert 'python-version: "3.12"' in text
    assert "workflow_dispatch:" in text
    assert '"v4*"' in text
    assert "build_standalone.ps1" in text
    assert "requirements.lock.txt" in text
    assert "FBA_Smart_Tool_V4_便携版.zip" in text
    assert "contents: read" in text
    assert "contents: write" not in text
    assert "action-gh-release" not in text
    assert "gh release" not in text
    assert "secrets." not in text
    doc = (ROOT / "docs" / "delivery" / "PORTABLE_WINDOWS_CI.md").read_text(encoding="utf-8")
    assert "FBA_Smart_Tool_V4_便携版.zip" in doc
    assert "FBA_Smart_Tool_V4_Portable.zip" in doc
    assert "Run workflow" in doc
    assert "不要在 Linux 上解压再重新压缩" in doc
    assert "不会创建或发布 GitHub Release" in doc
    assert "首次启动崩溃根因与防再发" in doc
    assert "test_factory_policy_defaults_are_in_whitelist_and_datas" in doc
    assert "39569887016" in doc


def test_portable_pr_paths_do_not_filter_tags_or_dispatch():
    """PR builds only for packaging paths. Tag pushes and workflow_dispatch stay unconditional."""
    import yaml

    text = (ROOT / ".github" / "workflows" / "portable-windows.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    # PyYAML 1.1 treats the bare key "on" as boolean true.
    triggers = data["on"] if "on" in data else data[True]
    assert list(triggers) == ["workflow_dispatch", "pull_request", "push"]
    assert triggers["workflow_dispatch"] in (None, {})

    pull = triggers["pull_request"]
    assert "paths-ignore" not in pull
    paths = pull["paths"]
    assert "backend/**" in paths
    assert "frontend/**" in paths
    assert "packaging/**" in paths
    assert ".github/workflows/portable-windows.yml" in paths
    # Inverse patterns (paths-ignore equivalent). They must follow the positive ones.
    for pattern in ("!docs/**", "!*.md", "!review/**"):
        assert pattern in paths
        assert paths.index("backend/**") < paths.index(pattern)

    push = triggers["push"]
    assert push["tags"] == ["v4*"]
    assert "paths" not in push
    assert "paths-ignore" not in push
    assert "branches" not in push


_WHEN = datetime(2026, 10, 26, 17, 30, tzinfo=timezone.utc)
_PINNED_USE = re.compile(
    r"^\s*uses:\s+[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}\s+#\s+v\d+\.\d+\.\d+\s*$"
)


def _quiet_runner(args):
    assert args[:2] == ["git", "describe"], args
    return ""


def test_buildinfo_records_tag_push_toolchain_and_run_id(tmp_path):
    def runner(args):
        raise AssertionError(args)

    env = {
        "GITHUB_SHA": "a" * 40,
        "GITHUB_REF_TYPE": "tag",
        "GITHUB_REF_NAME": "v4.0.1",
        "GITHUB_RUN_ID": "4242",
        "GITHUB_ACTIONS": "true",
        "BUILDINFO_PYTHON_VERSION": "Python 3.12.8",
        "BUILDINFO_NODE_VERSION": "v22.14.0",
    }
    info = FIN.resolve_buildinfo(env, now=_WHEN, runner=runner)
    assert info["git_sha"] == "a" * 40
    assert info["git_tag"] == "v4.0.1"
    assert info["github_run_id"] == "4242"
    assert info["built_at_utc"] == "2026-10-26T17:30:00Z"
    assert info["python_version"] == "3.12.8"
    assert info["node_version"] == "v22.14.0"
    assert info["app_version"] == "V4"
    text = FIN.format_buildinfo(info)
    assert text.startswith("# ")
    for key in FIN.BUILDINFO_FIELDS:
        assert f"{key}=" in text
    path = FIN.write_buildinfo(tmp_path, env=env, now=_WHEN)
    assert path.name == "BUILDINFO.txt"
    assert path.read_bytes().endswith(b"\n")
    assert b"\r" not in path.read_bytes()
    assert path.read_text(encoding="utf-8") == text


def test_buildinfo_leaves_tag_empty_on_pull_request():
    def runner(args):
        assert args[:2] == ["git", "describe"]
        return ""

    info = FIN.resolve_buildinfo(
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_SHA": "b" * 40,
            "GITHUB_REF_TYPE": "branch",
            "GITHUB_REF_NAME": "cursor/pin-actions-buildinfo",
            "GITHUB_RUN_ID": "99",
            "BUILDINFO_PYTHON_VERSION": "3.12.8",
            "BUILDINFO_NODE_VERSION": "v22.14.0",
        },
        now=_WHEN,
        runner=runner,
    )
    assert info["git_sha"] == "b" * 40
    assert info["git_tag"] == ""
    assert info["github_run_id"] == "99"


def test_buildinfo_uses_exact_local_tag_and_unknown_node():
    def runner(args):
        if args[:3] == ["git", "describe", "--tags"]:
            return "v4.0.1"
        if args[:2] == ["git", "rev-parse"]:
            return "c" * 40
        raise AssertionError(args)

    info = FIN.resolve_buildinfo(
        {"BUILDINFO_PYTHON_VERSION": "3.12.8"},
        now=_WHEN,
        runner=runner,
        which=lambda _name: None,
    )
    assert info["git_sha"] == "c" * 40
    assert info["git_tag"] == "v4.0.1"
    assert info["github_run_id"] == ""
    assert info["node_version"] == "unknown"


def test_buildinfo_rejects_multiline_fields():
    with pytest.raises(SystemExit, match="换行"):
        FIN.resolve_buildinfo(
            {
                "GITHUB_SHA": "ab\ncd",
                "GITHUB_REF_TYPE": "tag",
                "GITHUB_REF_NAME": "v4.0.1",
                "BUILDINFO_PYTHON_VERSION": "3.12.8",
                "BUILDINFO_NODE_VERSION": "v22.0.0",
            },
            now=_WHEN,
            runner=_quiet_runner,
        )


def test_portable_zip_requires_buildinfo_fields(tmp_path):
    assert f"{FIN.ZIP_PREFIX}/{FIN.BUILDINFO_NAME}" in FIN._required_zip_members()
    out = tmp_path / "FBA_Smart_Tool"
    out.mkdir()
    (out / "FBA_Smart_Tool.exe").write_bytes(b"MZ")
    env = {
        "GITHUB_SHA": "d" * 40,
        "GITHUB_REF_TYPE": "tag",
        "GITHUB_REF_NAME": "v4.0.1",
        "GITHUB_RUN_ID": "7",
        "BUILDINFO_PYTHON_VERSION": "3.12.8",
        "BUILDINFO_NODE_VERSION": "v22.14.0",
    }
    FIN.write_buildinfo(out, env=env, now=_WHEN)
    zip_path = tmp_path / "with-buildinfo.zip"
    FIN.write_utf8_zip(out, zip_path)
    required = [f"FBA_Smart_Tool/{FIN.BUILDINFO_NAME}"]
    FIN.verify_portable_zip(zip_path, required)
    with zipfile.ZipFile(zip_path) as zf:
        body = zf.read(required[0]).decode("utf-8")
    assert "git_sha=" + "d" * 40 in body
    assert "git_tag=v4.0.1" in body
    assert "github_run_id=7" in body

    broken = out / FIN.BUILDINFO_NAME
    broken.write_text("git_sha=only\n", encoding="utf-8")
    bad_zip = tmp_path / "bad-buildinfo.zip"
    FIN.write_utf8_zip(out, bad_zip)
    with pytest.raises(SystemExit, match="git_tag"):
        FIN.verify_portable_zip(bad_zip, required)


def test_workflow_actions_are_pinned_to_commit_shas():
    names = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
    assert names == ["ci.yml", "portable-windows.yml"]
    for name in names:
        text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        uses = [line for line in text.splitlines() if "uses:" in line]
        assert uses, name
        for line in uses:
            assert _PINNED_USE.match(line), line
            assert "@v" not in line.split("#", 1)[0]
    portable = (ROOT / ".github" / "workflows" / "portable-windows.yml").read_text(encoding="utf-8")
    assert "BUILDINFO_NODE_VERSION" in portable
    assert "BUILDINFO_PYTHON_VERSION" in portable
    assert "BUILDINFO.txt" in portable
    assert "fetch-tags: true" in portable
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "TODO" in ci
    assert "--deselect tests/release/test_techdebt.py::test_root_docs_are_not_duplicated" in ci
    assert (
        "--deselect tests/scan/test_no_real_data_in_repo.py::test_whitelist_templates_exist_and_text_scan_matches_baseline"
        in ci
    )
    ps1 = (ROOT / "scripts" / "build_standalone.ps1").read_text(encoding="utf-8-sig")
    assert "BUILDINFO.txt" in ps1
    doc = (ROOT / "docs" / "delivery" / "PORTABLE_WINDOWS_CI.md").read_text(encoding="utf-8")
    assert "BUILDINFO.txt" in doc
    assert "616e939e" in doc
    releasing = (ROOT / "docs" / "RELEASING.md").read_text(encoding="utf-8")
    assert "BUILDINFO.txt" in releasing
    maintaining = (ROOT / "docs" / "MAINTAINING.md").read_text(encoding="utf-8")
    assert "commit SHA" in maintaining or "40 位" in maintaining
    assert "secret scanning" in maintaining


def test_dependabot_tracks_github_actions_only():
    import yaml

    path = ROOT / ".github" / "dependabot.yml"
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    updates = data["updates"]
    assert [item["package-ecosystem"] for item in updates] == ["github-actions"]
    assert updates[0]["directory"] == "/"
    assert updates[0]["schedule"]["interval"] == "weekly"
    for item in updates:
        assert "auto-merge" not in item
        assert "automerge" not in item
    lowered = text.lower()
    assert "npm" not in lowered
    assert "pip" not in lowered
    assert "auto-merge" not in lowered
    assert "automerge" not in lowered
