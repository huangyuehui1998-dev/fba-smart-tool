"""PR-0：验收脚本在干净仓库上应复现 11 项、跳过 1 项（真实 PDF）。

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
    fixed = {"R1/N-08", "N-07", "N-02", "D-01", "R3"}
    assert {code for code, tag in status.items() if tag == "NOT REPRODUCED"} == fixed, out
    assert status["R2 真实第13批CL2"] == "SKIPPED"
    assert sum(tag == "REPRODUCED" for tag in status.values()) == 6, out
