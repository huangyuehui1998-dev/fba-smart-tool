"""PR-2a：交叉校验与过期屏蔽已修复；其余项仍复现。真实 PDF 为 SKIPPED。

默认不进门禁。运行：pytest -m acceptance
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "backend" / "tests" / "acceptance" / "repro_code_review.py"


@pytest.mark.acceptance
def test_acceptance_baseline_eleven_reproduced_one_skipped():
    env = os.environ.copy()
    env["FBA_DISABLE_SCHEDULER"] = "1"
    env.pop("FBA_APP_DATA_DIR", None)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--src", str(ROOT), "--realdata", str(ROOT / "missing-realdata")],
        cwd=str(ROOT / "backend"),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    out = proc.stdout + "\n" + proc.stderr
    assert proc.returncode == 0, out
    tags = re.findall(r"^\[(REPRODUCED|NOT REPRODUCED|SKIPPED)\] (.+?):", out, flags=re.M)
    status = {code: tag for tag, code in tags}
    fixed = {
        "R1/N-08",
        "N-07",
        "N-02",
        "D-01",
        "D-03a 单SKU箱配Mixed箱唛",
        "D-03b 箱唛SKU/数量未识别",
        "D-04 重复箱唛",
        "R4 首次进入即过期（静态）",
    }
    assert {code for code, tag in status.items() if tag == "NOT REPRODUCED"} == fixed, out
    assert status["R2 真实第13批CL2"] == "SKIPPED"
    assert sum(tag == "REPRODUCED" for tag in status.values()) == 3, out
