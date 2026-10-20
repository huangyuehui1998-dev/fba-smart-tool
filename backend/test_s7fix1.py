"""S7-fix1：九方同城多仓、外箱号更正入口、坏 JSON 用户配置提示。"""
from __future__ import annotations

import io
import json
from pathlib import Path

import openpyxl
import pytest
from fastapi.testclient import TestClient

HERE = Path(__file__).resolve().parent
INP = HERE / "tests/golden/samples/inputs"
B7 = INP / "第7批-FBA19GVFX5SC.csv"


@pytest.fixture()
def wh_db():
    from fba_tool.master_db import init_master_db
    from fba_tool.warehouse_db import apply_warehouse_import
    wh = HERE / "tests/fixtures/warehouse/fba_warehouse_qiluo.xlsx"
    if not wh.is_file():
        pytest.skip(f"需要 box realdata: {wh}")
    init_master_db()
    apply_warehouse_import(wh.read_bytes(), "q.xlsx")


def _client():
    from main import app
    return TestClient(app)


# ---------------------------------------------------------------- 1. 同城多仓：用 CSV 仓库代码，定不下来时给候选
def test_resolve_uses_csv_code_when_city_has_many(wh_db):
    from routers.invoice_export import resolve_export_warehouse
    assert resolve_export_warehouse("jiufang", "", "LAS VEGAS, NV", "VGT2") == ("VGT2", "CSV 仓库代码（配送地址同城多仓）")
    assert resolve_export_warehouse("jiufang", "las7", "LAS VEGAS, NV", "VGT2")[0] == "LAS7"   # 界面指定优先


def test_resolve_raises_with_candidates_when_csv_code_not_in_city(wh_db):
    from routers.invoice_export import WarehouseUndecided, resolve_export_warehouse
    with pytest.raises(WarehouseUndecided) as e:
        resolve_export_warehouse("jiufang", "", "LAS VEGAS, NV", "UNKN")
    assert {"VGT2", "LAS7", "IVSE"} <= set(e.value.candidates)
    assert resolve_export_warehouse("send", "", "LAS VEGAS, NV", "UNKN") == ("", "")


def test_api_batch7_vgt2_no_longer_422(wh_db):
    r = _client().post("/api/invoice-export/preview", data={"forwarder_id": "jiufang", "order_no": "X"},
                       files={"csv_file": (B7.name, B7.read_bytes())})
    assert r.status_code != 422, r.text
    # 产品库里没有这批 SKU → 409 拦截，但拦截原因里没有仓库问题
    if r.status_code == 409:
        assert "仓库" not in r.json()["detail"]
    else:
        assert r.json()["warehouse"] == "VGT2"


def test_api_undecided_returns_candidates_for_selector(wh_db):
    raw = B7.read_bytes().decode("utf-8-sig")
    raw = raw.replace("VGT2", "ZZZZ")  # 货件名称里的仓库代码对不上 → 只能让用户选
    r = _client().post("/api/invoice-export/preview", data={"forwarder_id": "jiufang"},
                       files={"csv_file": ("x.csv", raw.encode("utf-8"))})
    assert r.status_code == 422
    j = r.json()
    assert "请在面板上选择仓库" in j["detail"] and "VGT2" in j["warehouse_candidates"]


# ---------------------------------------------------------------- 4. 外箱号更正：按“多出的 FBA 箱号 → 箱序号”提交也能生效
def _box_xlsx(ids):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["序号", "外箱号", "单箱实重", "长", "宽", "高"])
    for i, b in enumerate(ids, 1):
        ws.append([i, b, 10.0 + i, 50, 40, 30])
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_box_id_fix_accepts_fba_key_from_panel():
    from fba_tool.invoice_rules import read_jiufang_box_data
    data = _box_xlsx([1, 2, 12])
    sid = "FBA19SC5CCXC"
    plain = read_jiufang_box_data(data, sid)
    assert f"{sid}U000012" in plain
    fixed = read_jiufang_box_data(data, sid, box_id_fix={f"{sid}U000012": 3})
    assert f"{sid}U000003" in fixed and f"{sid}U000012" not in fixed
    assert read_jiufang_box_data(data, sid, box_id_fix={"12": 3}).keys() == fixed.keys()  # 原写法仍可用


# ---------------------------------------------------------------- 3. 坏 JSON 用户配置：记日志 + 接口提示，不再静默
@pytest.mark.parametrize("name", ["user_settings.json", "formulas.json"])
def test_bad_user_config_is_reported(name, caplog):
    from fba_tool import user_config
    from fba_tool.app_paths import resolve_config_write
    p = resolve_config_write(name)
    p.write_text("{bad", encoding="utf-8")
    try:
        with caplog.at_level("WARNING"):
            user_config.load_settings(force=True)
            user_config.load_formulas(force=True)
        assert name in user_config.config_errors()
        assert any(name in r.getMessage() and "格式错误" in r.getMessage() for r in caplog.records)
        c = _client()
        j = c.get("/api/config/errors").json()
        assert not j["ok"] and any(e["file"] == name and "第 1 行" in e["message"] for e in j["errors"])
        path = "/api/config/settings" if name == "user_settings.json" else "/api/config/formulas"
        r = c.get(path)
        assert r.status_code == 200 and "X-Config-Warning" in r.headers   # 仍可用（出厂值兜底），但带提示
        p.write_text("{}", encoding="utf-8")
        assert c.get("/api/config/errors").json()["ok"]                  # 改好后提示消失
    finally:
        p.unlink(missing_ok=True)
        user_config.load_settings(force=True)
        user_config.load_formulas(force=True)


def test_good_config_no_warning():
    from fba_tool import user_config
    user_config.load_settings(force=True)
    assert "user_settings.json" not in user_config.config_errors()
