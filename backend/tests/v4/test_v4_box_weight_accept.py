"""U5-M2-P3 箱规毛重：合成边界。≠箱规超重已关，≠Publish。

Accept 主锚点是箱规向导 + 箱规库硬限，不是 L-FBA / Step2：

- 向导 ``OVERWEIGHT_KG`` 现为 23：超过才提示，不阻断保存（24 kg、恰好 70 kg）。
- 箱规库硬限 70 kg：恰好 70.00 可保存（200）；大于 70 不能保存，接口 422，
  文案含「不能大于 70」（70.1 / 80）。
- 政策内部预警约 22.5 kg（``user_settings`` / L-FBA / Step2）只作旁证。
  22.5 kg 不得误判为库硬限；不要把这条旁证并进 W1–W4。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from test_masterdata_rules import _isolated

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "synthetic" / "box_weight" / "cases.json"
WIZARD = ROOT / "frontend" / "src" / "lib" / "carton-wizard.ts"
DOC_SENTENCE = (
    "箱规毛重超过内部预警（约 22.5/23 kg）仍可继续，只提示不拦截；"
    "箱规库单箱毛重硬限为 70 kg，超过不能保存，接口返回 422。"
)
_OVER_KG = re.compile(r"^const OVERWEIGHT_KG = (?P<n>\d+(?:\.\d+)?);$", re.M)
_HARD_KG = re.compile(r"^const API_GROSS_MAX_KG = (?P<n>\d+(?:\.\d+)?);$", re.M)


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _wizard_limits() -> tuple[float, float]:
    text = WIZARD.read_text(encoding="utf-8")
    over = _OVER_KG.findall(text)
    hard = _HARD_KG.findall(text)
    assert over == ["23"], text
    assert hard == ["70"], text
    assert "if (gross > API_GROSS_MAX_KG)" in text
    assert "else if (gross > OVERWEIGHT_KG)" in text
    assert "超过系统上限 ${API_GROSS_MAX_KG} kg，无法保存" in text
    assert "超过 23 kg，请核对是否超重" in text
    return float(over[0]), float(hard[0])


def _wizard_band(gross: float, overweight_kg: float, hard_kg: float) -> str:
    if gross > hard_kg:
        return "blocker"
    if gross > overweight_kg:
        return "warn"
    return "under_wizard_warn"


def _spec(sku: str, gross_kg) -> dict:
    return {
        "sku": sku,
        "spec_name": "合成边界",
        "length_cm": 40,
        "width_cm": 30,
        "height_cm": 20,
        "qty_per_carton": 10,
        "gross_kg": gross_kg,
        "source": "manual",
    }


def test_api_boundaries_match_wizard_bands(monkeypatch, tmp_path):
    _isolated(monkeypatch, tmp_path)
    from main import create_app

    client = TestClient(create_app())
    payload = _payload()
    g3 = payload["g3"]
    overweight_kg, hard_kg = _wizard_limits()
    assert overweight_kg == g3["wizard_overweight_kg"] == 23
    assert hard_kg == g3["library_hard_max_kg"] == 70
    assert g3["policy_internal_warn_kg"] == 22.5
    assert overweight_kg != g3["policy_internal_warn_kg"]

    for case in payload["cases"]:
        gross = float(case["gross_kg"])
        assert _wizard_band(gross, overweight_kg, hard_kg) == case["wizard"], case["id"]
        response = client.post("/api/carton-specs", json=_spec(case["sku"], case["gross_kg"]))
        assert response.status_code == case["http"], (case["id"], response.text)
        if case["http"] == 200:
            body = response.json()
            assert body["sku"] == case["sku"]
            assert body["gross_kg"] == gross
            assert gross <= hard_kg
        else:
            detail = response.json()["detail"]
            text = detail["message"] + "".join(detail["fields"].values())
            assert case["error_contains"] in text, (case["id"], text)
            assert "不能大于 70" in text
            assert detail["fields"]["gross_kg"]


def test_user_manual_states_warn_versus_70kg_once():
    docs = (ROOT / "docs" / "使用说明.md").read_text(encoding="utf-8")
    portable = (ROOT / "packaging" / "使用说明.txt").read_text(encoding="utf-8")
    assert docs.count(DOC_SENTENCE) == 1
    assert portable.count(DOC_SENTENCE) == 1
