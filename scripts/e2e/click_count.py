"""从录入到报关导出的点击数。

--check 只核对步骤表和 docs/ux_baseline.json。
设置 FBA_E2E_URL 时用 Playwright 把当前路径再走一遍（需要已启动的前后端）。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / "docs" / "ux_baseline.json"

# 改前：四个文件分开下，SKU / 数量 / 装量 / 长宽高 / 毛重 / 订单号都要手改。
BASELINE_STEPS = [
    {"kind": "edit", "name": "SKU"},
    {"kind": "edit", "name": "发货总数"},
    {"kind": "edit", "name": "单箱装量"},
    {"kind": "edit", "name": "箱长"},
    {"kind": "edit", "name": "箱宽"},
    {"kind": "edit", "name": "箱高"},
    {"kind": "edit", "name": "单箱毛重"},
    {"kind": "click", "name": "解析"},
    {"kind": "click", "name": "下一步排箱"},
    {"kind": "click", "name": "自动排箱"},
    {"kind": "click", "name": "锁定方案"},
    {"kind": "click", "name": "下一步导出"},
    {"kind": "click", "name": "下载内部表"},
    {"kind": "click", "name": "下载 STA"},
    {"kind": "click", "name": "下载装箱单"},
    {"kind": "click", "name": "下载实操单"},
    {"kind": "click", "name": "下一步校验"},
    {"kind": "click", "name": "选择 CSV"},
    {"kind": "click", "name": "选择 PDF"},
    {"kind": "click", "name": "开始校验"},
    {"kind": "click", "name": "下一步发票"},
    {"kind": "click", "name": "下一步报关"},
    {"kind": "edit", "name": "订单号"},
    {"kind": "click", "name": "生成预览"},
    {"kind": "click", "name": "确认毛重"},
    {"kind": "click", "name": "导出报关"},
]

# 改后：一批粘贴算 1 次手工修改，四个文件一次导出。
CURRENT_STEPS = [
    {"kind": "edit", "name": "粘贴一批"},
    {"kind": "click", "name": "解析"},
    {"kind": "click", "name": "下一步排箱"},
    {"kind": "click", "name": "锁定方案"},
    {"kind": "click", "name": "下一步导出"},
    {"kind": "click", "name": "一键导出全部"},
    {"kind": "click", "name": "下一步校验"},
    {"kind": "click", "name": "开始校验"},
    {"kind": "click", "name": "进入报关"},
    {"kind": "edit", "name": "订单号"},
    {"kind": "click", "name": "导出报关"},
]


def tally(steps: list[dict]) -> dict[str, int]:
    return {
        "clicks": sum(1 for step in steps if step["kind"] == "click"),
        "manual_cell_edits": sum(1 for step in steps if step["kind"] == "edit"),
    }


def check() -> None:
    recorded = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline = tally(BASELINE_STEPS)
    current = tally(CURRENT_STEPS)
    assert recorded["baseline"] == baseline, (recorded["baseline"], baseline)
    assert recorded["current"] == current, (recorded["current"], current)
    assert current["clicks"] <= baseline["clicks"] * 0.5
    assert current["manual_cell_edits"] <= baseline["manual_cell_edits"] * 0.5
    print(json.dumps({"baseline": baseline, "current": current}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check()
    if args.check:
        return


if __name__ == "__main__":
    main()
