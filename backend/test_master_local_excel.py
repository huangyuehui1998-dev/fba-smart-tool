"""本地 Excel 批量编辑同步测试。"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from fba_tool.master_db import get_product_by_sku, init_master_db, upsert_product
from fba_tool.master_local_excel import (
    LOCAL_EXCEL_FILENAME,
    export_master_to_local_excel,
    local_excel_path,
    sync_local_excel_to_db,
    _dataframe_to_records,
)


@pytest.fixture()
def isolated_app_data(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    return ad


def test_export_and_sync_roundtrip(isolated_app_data):
    upsert_product(
        {
            "sku": "EXCEL-A",
            "model_name": "型号A",
            "chinese_name": "报关A",
            "declared_value": 12.5,
        }
    )
    upsert_product({"sku": "EXCEL-B", "english_name": "Name B"})

    path, count = export_master_to_local_excel()
    assert count == 2
    assert path.name == LOCAL_EXCEL_FILENAME
    assert path.is_file()

    # 模拟用户在 Excel 中修改并保存
    df = pd.read_excel(path, dtype=object)
    df.loc[df["SKU"] == "EXCEL-A", "商品报关名称"] = "报关A-改"
    df.loc[df["SKU"] == "EXCEL-A", "中文名称(型号)"] = "型号A-改"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="产品主数据", index=False)

    result = sync_local_excel_to_db()
    assert result["upserted"] == 2

    rec = get_product_by_sku("EXCEL-A")
    assert rec is not None
    assert rec["chinese_name"] == "报关A-改"
    assert rec["model_name"] == "型号A-改"


def test_dataframe_to_records_rejects_unknown_headers():
    df = pd.DataFrame([{"品名": "x"}])
    with pytest.raises(ValueError, match="表头"):
        _dataframe_to_records(df)


def test_delete_product_by_sku(isolated_app_data):
    from fba_tool.master_db import delete_product_by_sku

    upsert_product({"sku": "TEST-DEL", "chinese_name": "x"})
    assert delete_product_by_sku("TEST-DEL") is True
    assert get_product_by_sku("TEST-DEL") is None
    assert delete_product_by_sku("TEST-DEL") is False
