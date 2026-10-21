#!/bin/sh
# 在 git archive 出来的临时目录里跑箱侧冒烟。真实数据目录只在运行时读取，不进仓库。
set -eu
ROOT=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUN=$(mktemp -d)
git -C "$ROOT" archive --format=tar HEAD | tar -x -C "$RUN"
git -C "$ROOT" rev-parse HEAD > "$RUN/COMMIT.txt"
cd "$RUN/backend"
export FBA_REALDATA_DIR="${FBA_REALDATA_DIR:-/workspace/fba_tool/realdata}"
export FBA_APP_DATA_DIR="${FBA_APP_DATA_DIR:-$(mktemp -d)}"
export SMOKE_REPORT_PATH="$RUN/smoke_report.json"
python3 -m pytest -m realdata_smoke -q --tb=line
echo "smoke_report=$SMOKE_REPORT_PATH"
