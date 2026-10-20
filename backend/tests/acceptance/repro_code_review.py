"""代码评审问题复现脚本（重写版，2026-10-20）。

用法：FBA_DISABLE_SCHEDULER=1 python backend/tests/acceptance/repro_code_review.py [--src 仓库根]
默认 --src 是本脚本所在仓库的根目录。临时 FBA_APP_DATA_DIR，不碰正在跑的服务。
真实 PDF 只在 --realdata 里读取（不存在则该项 SKIPPED）；脚本本身不含真实数据。
输出：每项 REPRODUCED / NOT REPRODUCED / SKIPPED。
"""
from __future__ import annotations

import argparse
import collections
import glob
import os
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]

ap = argparse.ArgumentParser()
ap.add_argument("--src", default=str(_REPO))
ap.add_argument("--realdata", default="/workspace/fba_tool/realdata")
a = ap.parse_args()
tmp = tempfile.mkdtemp(prefix="fba_repro_")
os.environ["FBA_APP_DATA_DIR"] = tmp
os.environ.setdefault("FBA_DISABLE_SCHEDULER", "1")
sys.path.insert(0, os.path.join(a.src, "backend"))
os.chdir(os.path.join(a.src, "backend"))

import pandas as pd  # noqa: E402

results = []


def report(code, reproduced, detail):
    results.append((code, reproduced))
    tag = {True: "REPRODUCED", False: "NOT REPRODUCED", None: "SKIPPED"}[reproduced]
    print(f"[{tag}] {code}: {detail}")


def row(**kw):
    base = {
        "SKU简称": "TEST_A",
        "FNSKU": "X00TEST001",
        "发货总数": 100,
        "单箱装量": 4,
        "箱长(cm)": 40,
        "箱宽(cm)": 22,
        "箱高(cm)": 22,
        "单个重量(kg)": 0,
        "空纸箱重(kg)": 0.3,
        "单箱毛重(kg)": 1.8,
    }
    base.update(kw)
    return base


from fba_tool.data_processing import check_gross_weight_consistency, validate_step1, with_computed_columns  # noqa: E402

w = check_gross_weight_consistency(with_computed_columns(pd.DataFrame([row()])))
msg = w[0]["message"] if w else ""
fixed = bool(w) and w[0].get("kind") == "unit_weight_missing" and w[0].get("suggested_gross_kg") is None and "0.3" not in msg
report(
    "R1/N-08",
    not fixed,
    f"warnings={len(w)} msg={msg[:80]!r}（r3 期望：只出 kind=unit_weight_missing、suggested_gross_kg=None、不给建议值；单重填 0 视同缺失）",
)

df = with_computed_columns(pd.DataFrame([row(**{"单个重量(kg)": 0, "单箱毛重(kg)": 7.5})]))
g = float(df.loc[0, "预计总毛重(kg)"])
report("N-07", abs(g - 25 * 7.5) > 0.01, f"预计总毛重={g}（期望 25 箱×7.5=187.5）")

errs = validate_step1(pd.DataFrame([row(**{"单箱装量": 2.5})]))
report("N-02", not errs, f"validate_step1 errors={errs}（期望：拒绝 2.5）")

from fba_tool.boxing import box_metrics, dataframe_to_sku_rows, generate_box_plan, plans_to_editor_df  # noqa: E402

rows = [
    row(
        **{
            "SKU简称": s,
            "FNSKU": f"X00TEST00{i}",
            "发货总数": q,
            "单箱装量": 50,
            "箱长(cm)": 50,
            "箱宽(cm)": 40,
            "箱高(cm)": 30,
            "单个重量(kg)": u,
            "空纸箱重(kg)": 1.0,
            "单箱毛重(kg)": None,
        }
    )
    for i, (s, q, u) in enumerate([("TEST_A", 11, 1.0), ("TEST_B", 9, 1.0), ("TEST_C", 5, 0.48)])
]
sdf = with_computed_columns(pd.DataFrame(rows))
try:
    sku_rows = dataframe_to_sku_rows(sdf)
    plans = generate_box_plan(sku_rows, max_weight_kg=22.5)
    plans = plans[0] if isinstance(plans, tuple) else plans
    m = box_metrics(plans_to_editor_df(plans), sku_rows)
    mixed = m[m["SKU种类"] > 1]
    mx = float(mixed["毛重(kg)"].max()) if not mixed.empty else 0.0
    report("D-01", mx > 22.5, f"混装箱最大毛重={mx}kg（上限 22.5；尾数 11×1.0+9×1.0+5×0.48，皮重 1.0）")
except Exception as e:  # 签名变化时不误报
    report("D-01", None, f"调用失败：{e!r}")

from fba_tool import session_store  # noqa: E402

try:
    session_store.save_history_payload({"task_id": "../../REPRO_D05", "rows": [{"sku": "TEST_A"}]})
    hits = sorted(set(glob.glob(os.path.join(tmp, "**", "REPRO_D05.json"), recursive=True)))
    hist = str(session_store.HISTORY_DIR.resolve())
    escaped = [h for h in hits if not os.path.abspath(h).startswith(hist)]
    report("D-05", bool(escaped), f"写出位置={escaped or hits}")
    for h in hits:
        os.remove(h)
except Exception as e:
    report("D-05", False, f"被拒绝：{type(e).__name__}: {e}")

from fba_tool.fba_compliance import check_box_count_limit  # noqa: E402

r = check_box_count_limit(pd.DataFrame({"箱号": list(range(1, 161))}))
report("R3", bool(r) and "需拆分" in r["message"] and r.get("level") != "info", f"{r}")

from fba_tool.shipment_cross_check import cross_validate_pair  # noqa: E402
from fba_tool.shipment_parser import CsvShipment, PdfBoxPage  # noqa: E402

csv = CsvShipment(
    "FBATEST0001",
    "CLT2",
    1,
    box_data={1: {"TEST_A": 10}},
    box_fba_ids={1: "FBATEST0001U000001"},
)
e1 = cross_validate_pair(csv, [PdfBoxPage(0, "FBATEST0001", "FBATEST0001U000001", 1, is_mixed=True)], "CLT2", "FBATEST0001")
report("D-03a 单SKU箱配Mixed箱唛", not e1, f"errors={e1}")
e2 = cross_validate_pair(csv, [PdfBoxPage(0, "FBATEST0001", "FBATEST0001U000001", 1)], "CLT2", "FBATEST0001")
report("D-03b 箱唛SKU/数量未识别", not e2, f"errors={e2}")
dup = [PdfBoxPage(i, "FBATEST0001", "FBATEST0001U000001", 1, sku="TEST_A", qty=10) for i in range(2)]
e3 = cross_validate_pair(csv, dup, "CLT2", "FBATEST0001")
report("D-04 重复箱唛", not any("重复" in x for x in e3), f"errors={e3}")

from fba_tool import shipment_parser as sp  # noqa: E402

page = PdfBoxPage(0, "FBATEST0001", "FBATEST0001U000001", 1, warehouse_code="DOWD")
if hasattr(sp, "resolve_warehouse_with_warnings"):
    wh = sp.resolve_warehouse_with_warnings("CLT2", "x.pdf", [page] * 32)[0]
else:
    wh = sp.resolve_optimal_warehouse("CLT2", "x.pdf", [page] * 32)
report("R2 合成", wh != "CLT2", f"CSV=CLT2 + PDF 32 页 DOWD → {wh}")

pdfs = glob.glob(os.path.join(a.realdata, "batches", "*", "箱唛", "*CL2*.pdf"))
if pdfs:
    ps = sp.parse_pdf_pages(open(pdfs[0], "rb").read())
    c = collections.Counter(p.warehouse_code for p in ps)
    report("R2 真实第13批CL2", "DOWD" in c, f"页面仓码统计={dict(c)}")
else:
    report("R2 真实第13批CL2", None, "realdata 不存在")

inv = os.path.join(a.src, "frontend/src/lib/workflow-invalidation.ts")
ctx = os.path.join(a.src, "frontend/src/context/workflow-context.tsx")
masked = "effectiveStaleness" in open(ctx, encoding="utf-8").read() if os.path.exists(ctx) else False
report("R4 首次进入即过期（静态）", not masked, "context 未按产物屏蔽过期标记" if not masked else "已按产物屏蔽")

reproduced = sum(1 for _, flag in results if flag is True)
skipped = sum(1 for _, flag in results if flag is None)
print(f"\n汇总： {reproduced} 项复现 / {len(results)} 项；SKIPPED {skipped}；临时目录 {tmp}")
