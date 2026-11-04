import json
import urllib.parse
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from main import app
from fba_tool.routing_service import (
    strict_warehouse_from_filename,
    extract_ticket_rank,
    resolve_routing_warehouse,
)
from routers.routing import _process_routing_batch_sync

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "synthetic" / "rebox" / "unassigned_send_min.csv"


def _make_csv(wh_name: str = "ONT8") -> bytes:
    text = FIXTURE_PATH.read_text(encoding="utf-8-sig")
    modified = text.replace('"PLAIN"', f'"FBA-SHIPMENT-{wh_name}"')
    return modified.encode("utf-8-sig")


# =========================================================================
# 用例 1（AWD 仓识别）：如“第一票-IUSP.csv”、“第2票_STAR.csv”能 100% 精确提取 IUSP / STAR 并成功小计
# =========================================================================
def test_case1_awd_warehouse_extraction_and_subtotal():
    # 提取测试
    assert strict_warehouse_from_filename("第一票-IUSP.csv") == "IUSP"
    assert strict_warehouse_from_filename("第2票_STAR.csv") == "STAR"
    assert strict_warehouse_from_filename("AWD-IUSF.csv") == "IUSF"
    assert strict_warehouse_from_filename("AWD_IUSJ.csv") == "IUSJ"

    # 小计测试
    csv_bytes = _make_csv("OLD_CODE")
    records, _ = _process_routing_batch_sync([
        ("第一票-IUSP.csv", csv_bytes),
        ("第2票_STAR.csv", csv_bytes),
    ])

    subtotals = [r["仓库代码"] for r in records if "小计" in str(r.get("仓库代码"))]
    assert "IUSP 小计" in subtotals, f"缺少 IUSP 小计行: {subtotals}"
    assert "STAR 小计" in subtotals, f"缺少 STAR 小计行: {subtotals}"

    iusp_subtotal = next(r for r in records if r.get("仓库代码") == "IUSP 小计")
    assert iusp_subtotal["箱数"] > 0
    assert iusp_subtotal["总实重(kg)"] > 0


# =========================================================================
# 用例 2（未收录新大仓与海外仓识别）：如“第1票-ABQ2.csv”、“美西_VGT2.csv”、“PSC2.csv”、“LTN1-英国.csv”能 100% 精确提取
# =========================================================================
def test_case2_unlisted_and_overseas_warehouses():
    assert strict_warehouse_from_filename("第1票-ABQ2.csv") == "ABQ2"
    assert strict_warehouse_from_filename("美西_VGT2.csv") == "VGT2"
    assert strict_warehouse_from_filename("PSC2.csv") == "PSC2"
    assert strict_warehouse_from_filename("LTN1-英国.csv") == "LTN1"
    assert strict_warehouse_from_filename("01_XLX7.csv") == "XLX7"


# =========================================================================
# 用例 3（前缀与紧凑命名）：如“1ONT8.csv”、“02_LAX9.csv”、“第11票-SMF3.csv”能提取正确仓码与排序号
# =========================================================================
def test_case3_prefix_and_compact_naming():
    # 仓码识别
    assert strict_warehouse_from_filename("1ONT8.csv") == "ONT8"
    assert strict_warehouse_from_filename("02_LAX9.csv") == "LAX9"
    assert strict_warehouse_from_filename("第11票-SMF3.csv") == "SMF3"
    assert strict_warehouse_from_filename("票1_GYR2.csv") == "GYR2"

    # 票序识别
    assert extract_ticket_rank("1ONT8.csv") == 1
    assert extract_ticket_rank("02_LAX9.csv") == 2
    assert extract_ticket_rank("第11票-SMF3.csv") == 11
    assert extract_ticket_rank("第十一票.csv") == 11
    assert extract_ticket_rank("第二十五票.csv") == 25
    assert extract_ticket_rank("票1_GYR2.csv") == 1


# =========================================================================
# 用例 4（黑名单防误判）：如“50BOX.csv”、“CTN1.csv”不会把 BOX/CTN 误当成仓库代码
# =========================================================================
def test_case4_blacklist_tokens_guard():
    assert strict_warehouse_from_filename("50BOX.csv") == ""
    assert strict_warehouse_from_filename("CTN1.csv") == ""
    assert strict_warehouse_from_filename("batch_box1.csv") == ""
    assert strict_warehouse_from_filename("SKU2.csv") == ""
    assert strict_warehouse_from_filename("case1_ONT8.csv") == "ONT8"


# =========================================================================
# 用例 5（静默决胜无刺眼警告）：在 is_routing_mode=True 时，文件名覆盖旧 CSV 仓码不往返回头注入警告
# =========================================================================
def test_case5_silent_override_no_harsh_warning():
    # 验证底层函数成功产生审计覆盖信息
    wh, src, warn = resolve_routing_warehouse("ONT8", "第1票-ABQ2.csv", is_routing_mode=True)
    assert wh == "ABQ2"
    assert src == "文件名"
    assert warn is not None and "ABQ2" in warn and "ONT8" in warn

    # 验证 API 接口 Header 正常传递审计提示（前端已改造为温和提示，不再有 10s Toast 轰炸）
    client = TestClient(app)
    csv_bytes = _make_csv("ONT8")
    files = [
        ("files", ("20261104-ABQ2-第1票.csv", csv_bytes, "text/csv")),
        ("files", ("20261104-VGT2-第2票.csv", csv_bytes, "text/csv")),
    ]
    res = client.post("/api/routing/preview", files=files)
    assert res.status_code == 200
    warn_raw = res.headers.get("x-routing-warnings")
    assert warn_raw is not None
    warnings = json.loads(urllib.parse.unquote(warn_raw))
    assert any("ABQ2" in w and "ONT8" in w for w in warnings)


def test_case6_unkn_cartesian_product_prevention():
    text = FIXTURE_PATH.read_text(encoding="utf-8-sig")
    # 单文件基准数据
    recs1, _ = _process_routing_batch_sync([("unknown_a.csv", text.encode("utf-8-sig"))])
    qty1 = sum(int(r["发货总数"]) for r in recs1 if r.get("发货总数") and not str(r.get("仓库代码")).endswith("小计"))
    assert qty1 > 0

    # 两个同名/同序 UNKN 文件批量上传
    recs2, _ = _process_routing_batch_sync([
        ("第1票.csv", text.encode("utf-8-sig")),
        ("第1票.csv", text.encode("utf-8-sig")),
    ])
    qty2 = sum(int(r["发货总数"]) for r in recs2 if r.get("发货总数") and not str(r.get("仓库代码")).endswith("小计"))

    # 绝不能发生笛卡尔积成倍膨胀 (必须精准等于 qty1 * 2)
    assert qty2 == qty1 * 2, f"装箱数据发生交叉笛卡尔积膨胀: 期望 {qty1 * 2}, 实际 {qty2}"
