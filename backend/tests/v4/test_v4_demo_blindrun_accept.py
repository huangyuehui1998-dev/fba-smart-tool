"""U5-M2-P5 DEMO 盲跑：文档句子。≠DEMO/社区自助齐全，≠Publish。

不改产品逻辑。FAQ 关键句只在 OPEN_SOURCE 出现一次。
DEMO 可抄句在使用说明与 CONTRIBUTING 各出现一次；便携包只镜像样表那一句。
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OPEN_SOURCE = ROOT / "docs" / "OPEN_SOURCE.md"
MANUAL = ROOT / "docs" / "使用说明.md"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
README = ROOT / "README.md"
PORTABLE = ROOT / "packaging" / "使用说明.txt"
ACCEPT = ROOT / "review" / "ops_signoff" / "Accept-demo-blindrun.md"
RELEASING = ROOT / "docs" / "RELEASING.md"

SHA256 = "616e939e6beeeb647851b9ecaf91406c89b592566da5ea564e4489b80565bc63"
FAQ = (
    f"FBA_Smart_Tool_V4_Portable.zip` 的 SHA256 是 `{SHA256}",
    "脚注（双名）：二者在同一次构建里便携版同字节；只改文件名，不要解压后再压缩。",
    "仅维护者 Publish；ops/测试不 Publish。",
    "真实批次不入库；用 DEMO 样表/示例。",
    "命名 FBA 已交付 ≠ 刷箱同等验收。",
    "git 历史不改写；发布前跑 forbidden 扫描。",
    "STA 不代传 / 不接 SP-API 写。",
)
DEMO_NOTE = "发货录入样表.xlsx 在源码 templates，不进 Portable；Portable 用产品信息表示例 + 应用内 EXAMPLE 下载。"
NOT_A_REAL_ORDER = "DEMO-ORDER / DEMO-SKU 不可报关实单，标成「不可实单」。"
DEMO_LINE = "DEMO-SKU-001,X0DEMO0001,120,20,45,32,28,0.35,0.5"
PACK_STEP = "最小排箱可做：打开「2 排箱」，点「确认锁定方案并下一步」。"
INVOICE_STEP = "只选 SEND 或只选九方，再点「预览」。"
EXPORTER_RED = "缺出口商红字可演示。出厂未填出口商时，红字为「尚未配置出口商档案」。"
DEMO_HEADING = "## DEMO 盲跑（≤45 分钟）"
BANNED_ACCEPT_NAMES = (
    "Accept-demo-blind.md",
    "Accept-demo.md",
    "Accept-faq.md",
    "Signoff-demo.md",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _once(path: Path, sentence: str) -> None:
    assert _text(path).count(sentence) == 1, (path.name, sentence)


def test_faq_six_questions_once_in_open_source():
    text = _text(OPEN_SOURCE)
    assert text.count("## 常见六问") == 1
    assert text.count(SHA256) == 1
    assert SHA256 in _text(RELEASING)
    for sentence in FAQ:
        assert text.count(sentence) == 1, sentence
    for other in (MANUAL, CONTRIBUTING, README, PORTABLE, ACCEPT):
        body = _text(other)
        for sentence in FAQ:
            assert sentence not in body, (other.name, sentence)
    for n in range(1, 7):
        assert text.count(f"### Q{n}.") == 1
    assert "FBA_Smart_Tool_V4_便携版.zip" in text
    assert "便携版同字节" in text


def test_readme_points_at_faq_without_copying_answers():
    text = _text(README)
    assert text.count("「常见六问」") == 1
    assert "docs/OPEN_SOURCE.md" in text


def test_demo_short_steps_once_in_manual_and_contributing():
    for path in (MANUAL, CONTRIBUTING):
        _once(path, DEMO_HEADING)
        _once(path, NOT_A_REAL_ORDER)
        _once(path, DEMO_LINE)
        _once(path, PACK_STEP)
        _once(path, INVOICE_STEP)
        _once(path, EXPORTER_RED)
        _once(path, "「不可实单」")
        assert _text(path).count("本地规则解析") == 1
    manual = _text(MANUAL)
    assert manual.count(DEMO_NOTE) == 1
    assert "input_template_include_example" in manual
    assert "请先完成第 4 步：货件校验。" in manual
    assert "backend/templates/发货录入样表.xlsx" in manual
    assert "产品信息表_示例.csv" in manual


def test_portable_mirrors_sample_sheet_sentence_once():
    _once(PORTABLE, DEMO_NOTE)
    _once(MANUAL, DEMO_NOTE)
    for path in (OPEN_SOURCE, CONTRIBUTING, README, ACCEPT):
        assert DEMO_NOTE not in _text(path)


def test_accept_shell_is_pending_and_unique():
    text = _text(ACCEPT)
    assert "壳就绪 · 待测" in text
    for token in (
        "OPS5-O3-E",
        "OPS5-O9",
        "OPS4-O6",
        "OPS3-O6",
        "OPS3-O7",
        "U5-M2-P5",
        "M2_kickoff_2026-10-26.md",
        "序号 **6**",
        "DEMO-REF-01",
        "DEMO-REF-02",
        "DEMO-REF-03",
        "616e939e…",
        "≠DEMO/社区自助齐全",
        "≠Publish",
        "≠M2首包全部完成",
        "计费已改",
        "刷箱同等验收",
        "禁勾",
    ):
        assert token in text, token
    for n in range(1, 8):
        assert f"| D{n} |" in text
        row = next(line for line in text.splitlines() if line.startswith(f"| D{n} |"))
        assert row.endswith("| **待测** |"), row
    assert "当前禁止签「通过」" in text
    names = {path.name for path in (ROOT / "review").rglob("*.md")}
    assert "Accept-demo-blindrun.md" in names
    assert names.isdisjoint(BANNED_ACCEPT_NAMES)
