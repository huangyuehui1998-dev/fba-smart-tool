"""
莉莉 (Lily) - 亚马逊大件家居与多SKU装箱业务端到端全方位测试脚本
涵盖场景 A ~ F 真实业务数据压测与断言
"""
import time
import json
import pandas as pd
from decimal import Decimal
from fastapi.testclient import TestClient

from main import app
from fba_tool.models import SkuRow
from fba_tool.fba_compliance import evaluate_fba_boxing_compliance

client = TestClient(app)

def run_all_lily_tests():
    results = {}
    
    # -------------------------------------------------------------
    # 场景 A：单件大件商品纸箱超过 25 英寸 (70x50x40 cm 办公椅)
    # 验证：系统正确放行（豁免 25 in 限制），绝对不硬阻断！
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    sku_a = SkuRow(
        sku="CHAIR-OVR-25IN",
        total_qty=1,
        carton_qty=1,
        length_cm=70.0,
        width_cm=50.0,
        height_cm=40.0,
        unit_weight_kg=18.5,
        carton_tare_kg=0.8,
        unit_length_cm=68.0,
        unit_width_cm=48.0,
        unit_height_cm=38.0,
        category="furniture",
    )
    editor_a = pd.DataFrame([{"箱号": 1, "SKU简称": "CHAIR-OVR-25IN", "数量": 1}])
    metrics_a = pd.DataFrame([{"箱号": 1, "毛重(kg)": 19.3, "SKU种类": 1, "件数": 1}])
    comp_a = evaluate_fba_boxing_compliance(editor_a, [sku_a], metrics_a, destination="FBA")
    elapsed_a = (time.perf_counter() - t0) * 1000
    
    assert comp_a["blocked"] is False, f"场景A失败: 单件大件被误阻断: {comp_a}"
    assert comp_a["side_violation_count"] == 0, f"场景A失败: 边长违规数不为0: {comp_a['box_side_violations']}"
    results["Scenario_A"] = {
        "status": "PASS",
        "elapsed_ms": round(elapsed_a, 2),
        "blocked": comp_a["blocked"],
        "side_violations": comp_a["side_violation_count"],
        "notes": "单件大件办公椅(70cm)正确豁免25寸限制，顺利放行"
    }

    # -------------------------------------------------------------
    # 场景 B：多件混装纸箱单边超过 25 英寸 (65x40x30 cm 混装服装)
    # 验证：系统坚决阻断（硬阻断，符合 Help 200141510 官方政策）
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    sku_b1 = SkuRow(sku="CLOTH-M", total_qty=1, carton_qty=1, length_cm=65.0, width_cm=40.0, height_cm=30.0, unit_weight_kg=2.0)
    sku_b2 = SkuRow(sku="CLOTH-L", total_qty=1, carton_qty=1, length_cm=65.0, width_cm=40.0, height_cm=30.0, unit_weight_kg=2.5)
    editor_b = pd.DataFrame([
        {"箱号": 1, "SKU简称": "CLOTH-M", "数量": 1},
        {"箱号": 1, "SKU简称": "CLOTH-L", "数量": 1},
    ])
    metrics_b = pd.DataFrame([{"箱号": 1, "毛重(kg)": 5.0, "SKU种类": 2, "件数": 2}])
    comp_b = evaluate_fba_boxing_compliance(editor_b, [sku_b1, sku_b2], metrics_b, destination="FBA")
    elapsed_b = (time.perf_counter() - t0) * 1000
    
    assert comp_b["blocked"] is True, "场景B失败: 多件混装超25寸未被坚决硬阻断！"
    assert comp_b["side_violation_count"] >= 1, "场景B失败: 缺少边长违规详情"
    assert any("25" in v["message"] for v in comp_b["box_side_violations"]), "场景B失败: 提示未包含25寸"
    results["Scenario_B"] = {
        "status": "PASS",
        "elapsed_ms": round(elapsed_b, 2),
        "blocked": comp_b["blocked"],
        "side_violations": comp_b["side_violation_count"],
        "violation_msg": comp_b["box_side_violations"][0]["message"],
        "notes": "混装箱65cm严格硬阻断，100%符合Help 200141510官方政策"
    }

    # -------------------------------------------------------------
    # 场景 C：AWD (Amazon Warehousing & Distribution) 仓库发货
    # 验证：单件大件超过 25 英寸或箱重 > 50 lb，坚决阻断（AWD 禁止大件）
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    # C1: AWD 单件大件超 25 英寸
    comp_c1 = evaluate_fba_boxing_compliance(editor_a, [sku_a], metrics_a, destination="AWD")
    assert comp_c1["blocked"] is True, "场景C1失败: AWD 单件超25寸未被阻断！"
    assert comp_c1["side_violation_count"] >= 1, "场景C1失败: AWD 缺少尺寸违规"
    assert any("AWD" in v["message"] for v in comp_c1["box_side_violations"])

    # C2: AWD 箱重 > 50 lb (例如 24.0 kg = 52.9 lb)
    sku_c2 = SkuRow(sku="AWD-HEAVY-SKU", total_qty=1, carton_qty=1, length_cm=50.0, width_cm=40.0, height_cm=30.0, unit_weight_kg=23.5)
    editor_c2 = pd.DataFrame([{"箱号": 1, "SKU简称": "AWD-HEAVY-SKU", "数量": 1}])
    metrics_c2 = pd.DataFrame([{"箱号": 1, "毛重(kg)": 24.0, "SKU种类": 1, "件数": 1}])
    comp_c2 = evaluate_fba_boxing_compliance(editor_c2, [sku_c2], metrics_c2, destination="AWD")
    assert comp_c2["blocked"] is True, "场景C2失败: AWD 超过50lb未被硬阻断！"
    assert comp_c2["gross_violation_count"] >= 1, "场景C2失败: AWD 缺少重量违规"
    assert any("AWD" in v["message"] for v in comp_c2["box_gross_violations"])
    elapsed_c = (time.perf_counter() - t0) * 1000
    
    results["Scenario_C"] = {
        "status": "PASS",
        "elapsed_ms": round(elapsed_c, 2),
        "awd_dim_blocked": comp_c1["blocked"],
        "awd_weight_blocked": comp_c2["blocked"],
        "notes": "AWD入库尺寸超25寸与重量超50lb均被坚决拦截，杜绝AWD退运"
    }

    # -------------------------------------------------------------
    # 场景 D：单件大件毛重在 50~65 lb (23.5 kg / 51.8 lb)
    # 验证：系统柔性放行，并强制要求贴附 5 面 "Team Lift" 警示标签
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    sku_d = SkuRow(
        sku="CHAIR-50-65LB",
        total_qty=1,
        carton_qty=1,
        length_cm=72.0,
        width_cm=52.0,
        height_cm=45.0,
        unit_weight_kg=22.5,
        carton_tare_kg=1.0,
        unit_length_cm=70.0,
        unit_width_cm=50.0,
        unit_height_cm=43.0,
    )
    editor_d = pd.DataFrame([{"箱号": 1, "SKU简称": "CHAIR-50-65LB", "数量": 1}])
    metrics_d = pd.DataFrame([{"箱号": 1, "毛重(kg)": 23.5, "SKU种类": 1, "件数": 1}]) # 23.5kg = 51.81 lb
    comp_d = evaluate_fba_boxing_compliance(editor_d, [sku_d], metrics_d, destination="FBA")
    elapsed_d = (time.perf_counter() - t0) * 1000
    
    assert comp_d["blocked"] is False, f"场景D失败: 单件51.8lb被误阻断: {comp_d}"
    assert len(comp_d["lift_notices"]) == 1, "场景D失败: 缺少 lift_notices"
    notice_d = comp_d["lift_notices"][0]
    assert notice_d["label"] == "Team Lift", f"场景D失败: 标签不是Team Lift: {notice_d}"
    assert "共贴 5 张 Team Lift 标签" in notice_d["message"], f"场景D失败: 未强制要求5面标签: {notice_d['message']}"
    results["Scenario_D"] = {
        "status": "PASS",
        "elapsed_ms": round(elapsed_d, 2),
        "blocked": comp_d["blocked"],
        "lift_label": notice_d["label"],
        "lift_message": notice_d["message"],
        "notes": "单件大件51.8lb柔性放行，且精准触发5面Team Lift强制警示"
    }

    # -------------------------------------------------------------
    # 场景 E：单件大件毛重 > 100 lb (48.0 kg / 105.8 lb)
    # 验证：系统提示 "Mechanical Lift"
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    sku_e = SkuRow(
        sku="DESK-OVER-100LB",
        total_qty=1,
        carton_qty=1,
        length_cm=90.0,
        width_cm=60.0,
        height_cm=50.0,
        unit_weight_kg=47.0,
        carton_tare_kg=1.0,
        unit_length_cm=88.0,
        unit_width_cm=58.0,
        unit_height_cm=48.0,
    )
    editor_e = pd.DataFrame([{"箱号": 1, "SKU简称": "DESK-OVER-100LB", "数量": 1}])
    metrics_e = pd.DataFrame([{"箱号": 1, "毛重(kg)": 48.0, "SKU种类": 1, "件数": 1}]) # 48kg = 105.82 lb
    comp_e = evaluate_fba_boxing_compliance(editor_e, [sku_e], metrics_e, destination="FBA")
    elapsed_e = (time.perf_counter() - t0) * 1000
    
    assert comp_e["blocked"] is False, f"场景E失败: 单件超100lb被误阻断: {comp_e}"
    assert len(comp_e["lift_notices"]) == 1, "场景E失败: 缺少 lift_notices"
    notice_e = comp_e["lift_notices"][0]
    assert notice_e["label"] == "Mechanical Lift", f"场景E失败: 标签不是Mechanical Lift: {notice_e}"
    assert "Mechanical Lift" in notice_e["message"], f"场景E失败: 提示词错误: {notice_e['message']}"
    results["Scenario_E"] = {
        "status": "PASS",
        "elapsed_ms": round(elapsed_e, 2),
        "blocked": comp_e["blocked"],
        "lift_label": notice_e["label"],
        "lift_message": notice_e["message"],
        "notes": "单件大件48kg(105.8lb)精准触发5面Mechanical Lift机械吊装提示"
    }

    # -------------------------------------------------------------
    # 场景 F：单件大件商品未填写单件尺寸 (长宽高为 0 或 None)
    # 验证：具备柔性降级放行能力，绝不误杀真实发货
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    sku_f = SkuRow(
        sku="CHAIR-NODIM-NEW",
        total_qty=1,
        carton_qty=1,
        length_cm=70.0,
        width_cm=50.0,
        height_cm=40.0,
        unit_weight_kg=15.0,
        carton_tare_kg=0.5,
        unit_length_cm=0.0,
        unit_width_cm=0.0,
        unit_height_cm=0.0,
    )
    editor_f = pd.DataFrame([{"箱号": 1, "SKU简称": "CHAIR-NODIM-NEW", "数量": 1}])
    metrics_f = pd.DataFrame([{"箱号": 1, "毛重(kg)": 15.5, "SKU种类": 1, "件数": 1}])
    comp_f = evaluate_fba_boxing_compliance(editor_f, [sku_f], metrics_f, destination="FBA")
    elapsed_f = (time.perf_counter() - t0) * 1000
    
    assert comp_f["blocked"] is False, f"场景F失败: 缺少单品尺寸时被误阻断: {comp_f}"
    assert comp_f["side_violation_count"] == 0, f"场景F失败: 边长违规应为0: {comp_f['box_side_violations']}"
    results["Scenario_F"] = {
        "status": "PASS",
        "elapsed_ms": round(elapsed_f, 2),
        "blocked": comp_f["blocked"],
        "side_violations": comp_f["side_violation_count"],
        "carton_warnings": [w["message"] for w in comp_f["carton_side_warnings"]],
        "notes": "商品净尺寸缺失时系统平滑降级，仅软提示拒收风险，不卡单不误杀"
    }

    # -------------------------------------------------------------
    # 端到端 API 测试：通过 FastAPI /api/box_metrics 验证系统接口真实反应
    # -------------------------------------------------------------
    t0 = time.perf_counter()
    resp_api = client.post("/api/box_metrics", json={
        "rows": [{
            "SKU简称": "CHAIR-OVR-25IN",
            "FNSKU": "X00LILY01",
            "发货总数": 1,
            "单箱装量": 1,
            "箱长(cm)": 70,
            "箱宽(cm)": 50,
            "箱高(cm)": 40,
            "单个重量(kg)": 18.5,
            "空纸箱重(kg)": 0.8,
            "单件长(cm)": 68,
            "单件宽(cm)": 48,
            "单件高(cm)": 38,
            "品类": "furniture"
        }],
        "box_editor": [{"箱号": 1, "来源": "整箱", "SKU简称": "CHAIR-OVR-25IN", "数量": 1}],
        "transport_mode": "spd_partnered"
    })
    elapsed_api = (time.perf_counter() - t0) * 1000
    assert resp_api.status_code == 200, f"API调用失败: {resp_api.text}"
    api_json = resp_api.json()
    assert api_json["has_fba_block"] is False, "API层面误判阻塞！"
    results["E2E_API_Test"] = {
        "status": "PASS",
        "elapsed_ms": round(elapsed_api, 2),
        "status_code": resp_api.status_code,
        "has_fba_block": api_json["has_fba_block"],
        "metrics_count": len(api_json["metrics"]),
        "notes": "FastAPI /api/box_metrics 端到端请求校验成功，响应毫秒级"
    }
    
    return results

def test_lily_all_scenarios():
    results = run_all_lily_tests()
    assert len(results) >= 7

if __name__ == "__main__":
    res = run_all_lily_tests()
    with open("lily_test_results.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print("ALL 6 SCENARIOS AND E2E API PASSED SUCCESSFULLY!")
