"""为 Step 5 用户视角测试注入一条含 Step4 通过状态的历史任务。"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone

import urllib.request

from fba_tool.shipment_serialize import csv_shipment_to_dict
from test_customs_package import _sample_pair


def _post(url: str, body: dict) -> dict:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def build_snapshot() -> dict:
    pair = _sample_pair()
    parsed = csv_shipment_to_dict(pair.csv)
    dummy_b64 = base64.b64encode(b"step5-ui-test").decode()
    return {
        "task_id": str(uuid.uuid4()),
        "task_name": "Step5-UI测试任务",
        "step": 5,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "input_df": [
            {
                "SKU简称": "PAD-001",
                "SKU": "PAD-001",
                "发货总数": 180,
                "单个重量(kg)": 0.5,
            },
            {
                "SKU简称": "PAD-002",
                "SKU": "PAD-002",
                "发货总数": 50,
                "单个重量(kg)": 0.4,
            },
        ],
        "fnsku_overrides": {},
        "box_editor_df": [],
        "box_locked": False,
        "step4_validated": True,
        "step4_shipment_bundle": [
            {
                "shipment_id": pair.shipment_id,
                "warehouse": pair.warehouse_code,
                "csv_b64": dummy_b64,
                "pdf_b64": dummy_b64,
                "parsed_shipment": parsed,
            }
        ],
        "step4_status_lines": ["✅ Step5 UI 测试用快照"],
        "step4_validation_errors": [],
        "step4_forwarder_df": [],
        "react_step3_matrix": [],
        "react_step3_box_count": 2,
        "react_step3_sku_count": 2,
        "react_worker_packing_preview": [],
        "react_worker_packing_warehouses": [],
        "react_shipping_sheet": [],
        "react_shipping_sheet_legend": [],
        "react_actual_placement_fee": None,
        "react_metrics": [],
        "react_tail_pool": [],
        "react_has_overweight": False,
        "react_throw_ratio": 6000,
        "react_selected_shipment_id": pair.shipment_id,
        "react_invoice_draft": {
            "shipment_id": pair.shipment_id,
            "warehouse_code": pair.warehouse_code,
            "cells": [
                {"cell": "A8", "field_key": "sku", "value": "PAD-001"},
                {"cell": "B8", "field_key": "chinese_name", "value": "宠物垫"},
                {"cell": "C8", "field_key": "hs_code", "value": "6307909000"},
                {"cell": "D8", "field_key": "total_qty", "value": 180},
                {"cell": "E8", "field_key": "declared_price", "value": 35.51},
                {"cell": "F8", "field_key": "brand", "value": "DemoBrand"},
            ],
        },
        "react_invoice_template_base64": None,
    }


def main() -> None:
    snap = build_snapshot()
    result = _post("http://127.0.0.1:8013/api/tasks/history", {"name": snap["task_name"], "snapshot": snap})
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
