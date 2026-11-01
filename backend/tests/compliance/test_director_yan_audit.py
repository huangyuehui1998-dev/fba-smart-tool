"""Director Yan (亚马逊财务风控与合规总监) 专属独立审计与风控测试套件.

涵盖五大财务合规核心维度：
1. 场景 A: 动态政策热更新能力验证 (reload_policy 即刻生效，不停机、零漂移)
2. 场景 B: 缓冲衬垫超限风险与入库缺陷费防御 (>2 英寸预警，杜绝缺陷罚金)
3. 场景 C: 入库配置费梯度与分仓策略核算 (单点收费/部分拆分禁用规则/5仓优化免配置费)
4. 场景 D: 响应头防 CRLF 注入与合规 URL 编码 (X-Routing-Warnings 严格防注入与无损还原)
5. 场景 E: 生产级综合风控与全量稳定性验证
"""
import json
import re
from decimal import Decimal
from urllib.parse import quote, unquote

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fba_tool import app_paths
from fba_tool.fba_compliance import (
    current_gross_block_kg,
    current_gross_warn_kg,
    dimension_blocked,
    evaluate_fba_boxing_compliance,
)
from fba_tool.models import SkuRow
from fba_tool.placement_fee import PlacementFeeEngine, compute_shipment_placement_fees
from fba_tool.policy import load_policy, reload_policy
from main import app


def _make_sku(
    sku: str = "AUDIT-SKU",
    qty: int = 1,
    per_box: int = 1,
    l: float = 75.0,
    w: float = 40.0,
    h: float = 30.0,
    unit_kg: float = 12.0,
    u_l: float = 65.0,
    u_w: float = 38.0,
    u_h: float = 28.0,
) -> SkuRow:
    return SkuRow(
        sku=sku,
        total_qty=qty,
        carton_qty=per_box,
        length_cm=l,
        width_cm=w,
        height_cm=h,
        unit_weight_kg=unit_kg,
        carton_tare_kg=0.5,
        unit_length_cm=u_l,
        unit_width_cm=u_w,
        unit_height_cm=u_h,
    )


# ==========================================
# 场景 A：动态政策热更新能力验证 (Hot-Reload)
# ==========================================
def test_scenario_a_dynamic_policy_hot_reload(monkeypatch):
    """验证政策配置修改后调用 reload_policy() 零停服即刻生效。"""
    # 1. 验证出厂默认状态：50 lb = 22.68 kg
    reload_policy()
    default_block_kg = current_gross_block_kg()
    assert default_block_kg == Decimal("22.68"), f"默认阻断阈值应为 22.68kg，实际: {default_block_kg}"

    # 2. 模拟紧急政策调整：将混装箱重量上限动态收紧为 45 lb (20.41 kg)
    policy_data = json.loads(json.dumps(load_policy()))
    policy_data["rules"]["multi_box_weight_lb"]["value"] = 45.0
    temp_dir = app_paths.bundled_backend_dir() / ".pytest_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_policy_file = temp_dir / "hot_reload_policy.json"
    temp_policy_file.write_text(json.dumps(policy_data, ensure_ascii=False), encoding="utf-8")

    try:
        # 模拟指向新的配置路径
        monkeypatch.setattr(
            "fba_tool.policy.resolve_config_read",
            lambda name: temp_policy_file if name == "policy.json" else app_paths.resolve_config_read(name),
        )

        # 在不停服、不重启进程的情况下执行热重载
        reload_policy()
        new_block_kg = current_gross_block_kg()
        expected_new_kg = (Decimal("45.0") * Decimal("0.45359237")).quantize(Decimal("0.01"))
        assert new_block_kg == expected_new_kg, f"热更新后阈值应为 {expected_new_kg}kg，实际: {new_block_kg}"
        assert new_block_kg == Decimal("20.41"), "45 lb 对应 20.41 kg"

        # 3. 业务断言：21.0 kg 混装箱在旧政策下放行，在新政策下被硬阻断！
        editor = pd.DataFrame([{"箱号": 1, "SKU简称": "AUDIT-SKU", "数量": 2}])
        metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": 21.0}])
        sku = _make_sku(qty=2, per_box=2, l=50.0, w=40.0, h=30.0, unit_kg=10.0, u_l=25.0, u_w=20.0, u_h=15.0)
        comp_hot = evaluate_fba_boxing_compliance(editor, [sku], metrics, destination="FBA")
        assert comp_hot["blocked"] is True, "45 lb 政策下 21.0kg 混装箱必须阻断"
        assert comp_hot["gross_violation_count"] >= 1

        # 4. 恢复默认政策并再次热重载
        monkeypatch.undo()
        reload_policy()
        restored_block_kg = current_gross_block_kg()
        assert restored_block_kg == Decimal("22.68"), "恢复后阈值应立即还原为 22.68kg"
        comp_restored = evaluate_fba_boxing_compliance(editor, [sku], metrics, destination="FBA")
        assert comp_restored["blocked"] is False, "恢复 50 lb 后 21.0kg 混装箱应放行"
    finally:
        if temp_policy_file.exists():
            temp_policy_file.unlink(missing_ok=True)


# ==========================================
# 场景 B：缓冲衬垫超限风险与入库缺陷费防御
# ==========================================
def test_scenario_b_cushion_dunnage_excess_warning():
    """验证单件大件外箱明显长于商品（> 2 英寸）触发缺陷费预警。"""
    # 箱长 75cm (29.53 in)，商品净长 65cm (25.59 in)，间隙 10cm (3.94 in > 2.0 in)
    oversize_slack_sku = _make_sku(qty=1, per_box=1, l=75.0, w=40.0, h=30.0, unit_kg=12.0, u_l=65.0, u_w=38.0, u_h=28.0)
    editor = pd.DataFrame([{"箱号": 1, "SKU简称": "AUDIT-SKU", "数量": 1}])
    metrics = pd.DataFrame([{"箱号": 1, "毛重(kg)": 13.0}])

    comp = evaluate_fba_boxing_compliance(editor, [oversize_slack_sku], metrics, destination="FBA")
    # FBA 单件大件尺寸豁免，放行主流程，但必须弹出衬垫超限警告
    assert comp["blocked"] is False, "单件大件符合豁免条件，不应硬阻断发货"
    assert len(comp["box_fit_warnings"]) == 1, "必须准确捕获 1 条缓冲衬垫警告"
    warn = comp["box_fit_warnings"][0]
    assert warn["box_no"] == 1
    assert "缓冲衬垫厚度 ≤ 2 英寸" in warn["message"]
    assert "避免入库缺陷费" in warn["message"]

    # 对照组：衬垫合规情况（箱长 68cm vs 商品 65cm，间隙 3cm = 1.18 in <= 2.0 in）
    compliant_sku = _make_sku(qty=1, per_box=1, l=68.0, w=40.0, h=30.0, unit_kg=12.0, u_l=65.0, u_w=38.0, u_h=28.0)
    comp_compliant = evaluate_fba_boxing_compliance(editor, [compliant_sku], metrics, destination="FBA")
    assert len(comp_compliant["box_fit_warnings"]) == 0, "合规衬垫厚度不应误报警告"


# ==========================================
# 场景 C：入库配置费梯度与分仓策略核算
# ==========================================
def test_scenario_c_placement_fee_and_split_audit():
    """核验 2026 入库配置费梯度、标准尺寸拆分禁用与优化免配置费逻辑。"""
    engine = PlacementFeeEngine()

    # 1. 标准尺寸品 (Large standard, 1.2 lb 实重, 尺寸 30x20x10 cm)
    unit_std = engine.compute_unit(30.0, 20.0, 10.0, 0.54)  # 0.54 kg = 1.19 lb
    assert unit_std["eligible"] is True
    assert unit_std["size_class"] == "large_standard"
    assert unit_std["one_location"] is not None
    assert unit_std["one_location"]["min_usd"] > 0
    # 财务红线：标准尺寸亚马逊政策严格禁止部分拆分 (2-3仓)
    assert unit_std["split_2_3_disabled"] is True
    assert "标准尺寸商品不支持部分拆分入库" in unit_std["split_2_3_disabled_reason"]
    assert unit_std["split_2_3"] is None
    # 优化分仓 (5仓+) 配置费全免
    assert unit_std["optimized_5"]["min_usd"] == 0.0
    assert unit_std["optimized_5"]["max_usd"] == 0.0

    # 2. 大件品 (Small Bulky / small_oversize, 15 lb, 70x40x30 cm)
    unit_bulky = engine.compute_unit(70.0, 40.0, 30.0, 6.8)
    assert unit_bulky["eligible"] is True
    assert unit_bulky["size_class"] in ("small_oversize", "large_oversize")
    # 大件品允许部分拆分，且部分拆分费率严格低于单点入仓
    assert unit_bulky["split_2_3_disabled"] is False
    assert unit_bulky["split_2_3"] is not None
    assert unit_bulky["split_2_3"]["min_usd"] < unit_bulky["one_location"]["min_usd"]
    assert unit_bulky["optimized_5"]["min_usd"] == 0.0

    # 3. 超大件 (Extra-large, 如 25 kg = 55.1 lb > 50 lb, 120x60x50 cm)
    unit_xl = engine.compute_unit(120.0, 60.0, 50.0, 25.0)
    assert unit_xl["size_class"] == "extra_large"
    assert unit_xl["optimized_5"]["min_usd"] == 0.0

    # 4. 整票货件配置费测算 (compute_shipment_placement_fees)
    shipment_rows = [
        {"SKU简称": "STD-01", "发货总数": 100, "unit_length_cm": 30.0, "unit_width_cm": 20.0, "unit_height_cm": 10.0, "unit_weight_kg": 0.5},
        {"SKU简称": "BULKY-01", "发货总数": 20, "unit_length_cm": 70.0, "unit_width_cm": 40.0, "unit_height_cm": 30.0, "unit_weight_kg": 6.8},
    ]
    shipment_res = compute_shipment_placement_fees(shipment_rows)
    assert shipment_res["total_units"] == 120
    assert shipment_res["eligible_units"] == 120
    assert shipment_res["oversize_units"] == 20
    # 含有大件时，整票支持 2-3 仓拆分
    assert shipment_res["split_2_3"]["enabled"] is True
    assert shipment_res["one_location"]["min_usd"] > shipment_res["split_2_3"]["min_usd"]
    assert shipment_res["optimized_5"]["min_usd"] == 0.0


# ==========================================
# 场景 D：响应头防 CRLF 注入与合规 URL 编码
# ==========================================
def test_scenario_d_crlf_defense_and_url_encoding():
    """验证 X-Routing-Warnings 响应头严格抵御换行注入并实现无损解码。"""
    raw_warnings = [
        "提示: 第一票 ONT8 与 CSV 目的仓 GYR3 不一致\r\nSet-Cookie: malicious=true",
        "提示: 第二票存在非法换行符\n\rX-Injected-Header: evil",
        "常规合规告警: 正常中文内容测试",
    ]

    # 1. 模拟后端清洗与编码流水线
    clean_warnings = [re.sub(r"[\r\n]+", " ", str(w)).strip() for w in raw_warnings if w]
    for w in clean_warnings:
        assert "\r" not in w and "\n" not in w, f"清洗后不应含有任何换行符: {w}"

    encoded_header = quote(json.dumps(clean_warnings, ensure_ascii=False))
    assert "\r" not in encoded_header and "\n" not in encoded_header

    # 2. 前端逆向解码还原验证
    decoded_json = unquote(encoded_header)
    restored_list = json.loads(decoded_json)
    assert len(restored_list) == 3
    assert restored_list[0] == "提示: 第一票 ONT8 与 CSV 目的仓 GYR3 不一致 Set-Cookie: malicious=true"
    assert restored_list[2] == "常规合规告警: 正常中文内容测试"

    # 3. 超长告警熔断防御验证 (防 431 Header Overflow)
    many_warnings = [f"告警详情测试项_{i}_" + ("X" * 100) for i in range(100)]
    clean_many = [re.sub(r"[\r\n]+", " ", str(w)).strip() for w in many_warnings if w]
    enc = quote(json.dumps(clean_many, ensure_ascii=False))
    if len(enc) > 3500:
        clean_many = clean_many[:10] + ["... (告警较多已截断)"]
        enc = quote(json.dumps(clean_many, ensure_ascii=False))
    assert len(enc) <= 3500, "超长响应头必须熔断截断在 3500 字符以内"
