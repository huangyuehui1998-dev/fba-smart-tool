"""横向工人装箱表导出测试。"""
import pytest

from fba_tool.master_db import init_master_db
from fba_tool.shipment_parser import CsvShipment
from fba_tool.shipment_validator import ShipmentPair
from fba_tool.worker_packing_export import (
    build_worker_packing_horizontal_df,
    build_warehouse_worker_df,
    export_worker_packing_list,
    export_worker_packing_preview,
    ticket_label,
    _blocks_from_pairs,
    _boxes_from_pair,
)


@pytest.fixture(autouse=True)
def isolated_app_data(monkeypatch, tmp_path):
    ad = tmp_path / "app_data"
    ad.mkdir()
    monkeypatch.setattr("fba_tool.master_db._master_db_file", lambda: ad / "fba_master.db")
    monkeypatch.setattr("fba_tool.app_paths.app_data_dir", lambda: ad)
    init_master_db()
    return ad


def test_blocks_follow_pair_order():
    pairs = [
        _pair("GYR2", "FBA-A", "第五票外箱贴X-FBA-A-GYR2.pdf"),
        _pair("FWA4", "FBA-B", "第一票外箱贴Y-FBA-B-FWA4.pdf"),
        _pair("RDU2", "FBA-C", "第二票外箱贴Z-FBA-C-RDU2.pdf"),
    ]
    blocks = _blocks_from_pairs(pairs)
    assert [b[0] for b in blocks] == ["第一票 FWA4", "第二票 RDU2", "第五票 GYR2"]


def _pair(wh: str, sid: str = "FBA1", pdf_name: str = "") -> ShipmentPair:
    csv = CsvShipment(
        shipment_id=sid,
        warehouse_code=wh,
        box_count=2,
        box_data={1: {"SKU-A": 2}, 2: {"SKU-B": 1}},
        box_fba_ids={1: f"{sid}U000001", 2: f"{sid}U000002"},
    )
    return ShipmentPair(sid, wh, csv, None, pdf_name)  # type: ignore[arg-type]


def test_worker_product_name_uses_master():
    from fba_tool import worker_packing_export as wpe
    from fba_tool.master_db import upsert_product

    upsert_product(
        {
            "sku": "LONG-SKU-NAME-ABC",
            "model_name": "完整产品名称示例",
        }
    )
    assert wpe._worker_product_name("LONG-SKU-NAME-ABC") == "完整产品名称示例"
    assert wpe._product_label("LONG-SKU-NAME-ABC", 2) == "完整产品名称示例"


def test_warehouse_df_qty_and_fnsku_columns():
    pair = _pair("FWA4")
    boxes = _boxes_from_pair(pair)
    df = build_warehouse_worker_df(boxes)
    assert list(df.columns) == ["纸箱编号", "产品名称", "FNSKU", "数量"]
    sku_a_rows = df[df["产品名称"].astype(str).str.contains("SKU-A", na=False)]
    assert not sku_a_rows.empty
    assert str(sku_a_rows.iloc[0]["数量"]) == "2"


def test_warehouse_product_summary():
    pair = _pair("FWA4")
    boxes = _boxes_from_pair(pair)
    df = build_warehouse_worker_df(boxes)
    prod_lines = df.loc[
        df["产品名称"].astype(str).str.contains("共") & df["产品名称"].astype(str).str.endswith("箱"),
        "产品名称",
    ].astype(str).tolist()
    assert "【汇总】" in df["纸箱编号"].astype(str).values
    assert len(prod_lines) == 2


def test_horizontal_concat_ticket_columns():
    pairs = [
        _pair("FWA4", "FBA1", "第一票外箱贴-A-FBA1-FWA4.pdf"),
        _pair("GYR2", "FBA2", "第二票外箱贴-B-FBA2-GYR2.pdf"),
    ]
    df = build_worker_packing_horizontal_df(pairs)
    assert "第一票 FWA4_纸箱编号" in df.columns
    assert "第二票 GYR2_产品名称" in df.columns
    assert "第一票 FWA4_FNSKU" in df.columns
    assert "第二票 GYR2_数量" in df.columns


def test_export_preview_fast_path():
    pairs = [_pair("FWA4", "FBA1", "第二票外箱贴-FBA1-FWA4.pdf")]
    df = build_worker_packing_horizontal_df(pairs)
    rows = df.to_dict(orient="records")
    data = export_worker_packing_preview(rows, ["第二票 FWA4"])
    assert len(data) > 500


def test_export_bytes():
    data = export_worker_packing_list([_pair("FWA4")])
    assert len(data) > 500


if __name__ == "__main__":
    test_blocks_follow_pair_order()
    test_warehouse_df_qty_and_fnsku_columns()
    test_warehouse_product_summary()
    test_horizontal_concat_ticket_columns()
    test_export_preview_fast_path()
    test_export_bytes()
    print("ALL OK")
