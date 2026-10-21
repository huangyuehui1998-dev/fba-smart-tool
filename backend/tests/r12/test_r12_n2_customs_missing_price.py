"""N2：缺申报价时预览和导出都是 409，零售价和成本口径一样。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fba_tool.shipment_serialize import csv_shipment_to_dict
from test_customs_package import _sample_pair
from test_masterdata_rules import _isolated


def _body():
    pair = _sample_pair()
    return {
        "source": "shipment",
        "order_no": "T1",
        "workflow_json": {
            "shipments": [{
                "shipment_id": pair.shipment_id,
                "warehouse": pair.warehouse_code,
                "parsed_shipment": csv_shipment_to_dict(pair.csv),
            }],
        },
    }


@pytest.mark.parametrize("basis", ["retail", "cost"])
def test_preview_and_export_return_409_when_price_missing(monkeypatch, tmp_path, basis):
    _isolated(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "fba_tool.warehouse_db.get_default_rule_profile",
        lambda: {"declared_value_basis": basis},
    )
    from main import create_app

    client = TestClient(create_app())
    payload = _body()
    preview = client.post("/api/customs/preview", json=payload)
    exported = client.post("/api/customs/export", json=payload)
    for response in (preview, exported):
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["code"] == "DECLARED_VALUE_MISSING"
