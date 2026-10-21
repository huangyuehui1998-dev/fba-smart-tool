"""独立复算的合成用例。不使用第 13 批锚点，也不读 realdata。"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from tests.smoke.reference import (
    LayoutMissing,
    _measure_files,
    assemble,
    chargeable,
    cl2_net,
    parse_measure_file,
    round_up_half_kg,
    summarize_batch13,
)


def _book(path: Path, rows: list[list]) -> None:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)


def test_round_up_and_chargeable_do_not_use_product_code():
    assert round_up_half_kg("10.01") == Decimal("10.5")
    assert round_up_half_kg("10.50") == Decimal("10.5")
    assert chargeable("10", [10, 10, 10]) == Decimal("10.000")


def test_footer_bill_without_boxes_is_not_added(tmp_path):
    _book(tmp_path / "九方.xlsx", [
        ["外箱号", "运单号", "单箱实重", "长", "宽", "高"],
        ["FBATESTU000001", "WBTEST1", "10.25", 10, 10, 10],
        ["入库计费重", 10.5],
    ])
    parsed = parse_measure_file(tmp_path / "九方.xlsx")
    assert parsed["bills"]["WBTEST1"] == Decimal("10.50")
    assert len(parsed["boxes"]) == 1
    line = chargeable(parsed["boxes"][0]["weight"], parsed["boxes"][0]["dims"])
    assert round_up_half_kg(line) == Decimal("10.5")


def test_present_directory_without_layout_fails(tmp_path):
    (tmp_path / "note.txt").write_text("present", encoding="utf-8")
    with pytest.raises(LayoutMissing):
        assemble(tmp_path)


def _measure_book(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _book(path, [
        ["外箱号", "运单号", "单箱实重", "长", "宽", "高"],
        ["FBATESTU000001", "WBTEST1", "10.25", 10, 10, 10],
        ["入库计费重", 10.5],
    ])


def _amazon_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "包装箱重量（kg）,10\n"
        "包装箱长度（cm）,10\n"
        "包装箱宽度（cm）,10\n"
        "包装箱高度（cm）,10\n"
        "箱号,FBATESTU000001\n",
        encoding="utf-8",
    )


def _sta(root: Path) -> None:
    for batch, total in (("13", 2), ("14", 6), ("15", 1)):
        folder = root / "batches" / f"第{batch}批"
        folder.mkdir(parents=True, exist_ok=True)
        _book(folder / "Send to Amazon.xlsx", [[f"SKU总数：{total}"]])


def _entry(path: Path, tare: float | None = 0.3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _book(path, [
        ["SKU简称*", "发货总数*", "单箱装量*", "单个重量(kg)", "空纸箱重(kg)", "单箱毛重(kg)"],
        ["J-PETMAT-CAR-ZHENTOU-DEMO", 64, 2, None, tare, 8],
        ["J-PETMAT-CAR-TANZI-DEMO", 64, 2, None, tare, 8],
    ])


def _shipping(path: Path, carton_a: str, carton_b: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _book(path, [
        ["亚马逊 FBA 发货装箱单"],
        ["FBA 货件编号\n(Shipment ID)", "箱号\n(Carton No.)", "总毛重(KG)\n(Total G.W.)", "中文品名"],
        ["FBATESTCL2", carton_a, 150, "枕头"],
        ["FBATESTCL2", carton_b, 114, "毯子"],
        ["", "", 264, "合计 (Total)"],
    ])


def test_jiufang_bill_dir_assembles_cl2_net_254_4(tmp_path):
    batch = tmp_path / "batches" / "第13批"
    _measure_book(batch / "九方确认账单文件" / "单箱.xlsx")
    _amazon_csv(batch / "货件.csv")
    _shipping(batch / "发给工厂" / "发货表.xlsx", "1-18", "19-32")
    _entry(batch / "发货录入样表.xlsx")
    _sta(tmp_path)
    report = assemble(tmp_path)
    cl2 = report["cl2"]
    assert cl2["net"] == Decimal("254.4")
    assert cl2["boxes"] == 32
    assert cl2["gross"] == Decimal("264.0")
    assert cl2["tare"] == Decimal("0.3")
    assert "九方确认账单文件" in report["batch13"]["measure_files"][0]
    from fba_tool.customs_package import compute_net_weight

    product_net = Decimal(str(compute_net_weight(cl2["gross"], cl2["boxes"], [cl2["tare"]] * cl2["boxes"])))
    assert cl2["net"] == product_net == Decimal("254.4")


def test_legacy_measure_dir_still_parses(tmp_path):
    batch = tmp_path / "batches" / "第13批"
    _measure_book(batch / "货代计费重确认文件" / "九方.xlsx")
    _amazon_csv(batch / "货件.csv")
    summary = summarize_batch13(tmp_path)
    assert summary["bill_count"] == 1
    assert len(_measure_files(tmp_path)) == 1


def test_inbound_folder_is_not_a_measure_source(tmp_path):
    batch = tmp_path / "batches" / "第13批"
    _measure_book(batch / "货代入库数据" / "货代计费重确认文件" / "九方.xlsx")
    _amazon_csv(batch / "货件.csv")
    with pytest.raises(LayoutMissing, match="九方确认账单"):
        summarize_batch13(tmp_path)


def test_comma_box_numbers_and_csv_count_both_can_reach_254_4(tmp_path):
    batch = tmp_path / "batches" / "第13批"
    left = ",".join(str(i) for i in range(1, 17))
    right = ",".join(str(i) for i in range(17, 33))
    _shipping(batch / "发给工厂" / "发货表.xlsx", left, right)
    _entry(batch / "发货录入样表.xlsx")
    got = cl2_net(tmp_path)
    assert got["net"] == Decimal("254.4")
    assert got["boxes"] == 32
    assert "箱号" in got["detail"]

    root = tmp_path / "csv-case"
    batch = root / "batches" / "第13批"
    _shipping(batch / "发给工厂" / "发货表.xlsx", "见明细", "见明细")
    _entry(batch / "发货录入样表.xlsx")
    packing = batch / "装箱明细" / "第一票FBATESTCL2.csv"
    packing.parent.mkdir(parents=True)
    packing.write_text("货件编号,FBATESTCL2\n箱子数量,32\n", encoding="utf-8")
    from_csv = cl2_net(root)
    assert from_csv["net"] == Decimal("254.4")
    assert from_csv["boxes"] == 32
    assert "箱子数量" in from_csv["detail"]


def test_packaging_name_does_not_zero_box_total(monkeypatch, tmp_path):
    """箱号行后面的包装箱名称不能把真 FBA 箱唛盖掉，否则申报对不上、box_total 变成 0。"""
    root = tmp_path / "real"
    measure = root / "batches" / "第13批" / "九方确认账单文件"
    measure.mkdir(parents=True)
    _book(measure / "九方.xlsx", [
        ["外箱号", "运单号", "单箱实重", "长", "宽", "高"],
        ["FBATEST01U000001", "WBTEST1", 20, 40, 40, 40],
        ["入库计费重", 20],
    ])
    csv_path = root / "batches" / "第13批" / "ship.csv"
    csv_path.write_text(
        "\n".join([
            '"货件编号","FBATEST01"',
            '"货件名称","S01"',
            '"配送地址","STEP45VILLE, ZZ"',
            '"箱子数量","1"',
            "",
            '"单件商品（1 箱）"',
            '"SKU","商品名称","ASIN","FNSKU","状况","预处理类型","商品总数","箱子 1 的商品数量"',
            '"S01-SKU","rod","B0S01TEST1","X00TESTS01","新品","无","1","1"',
            "",
            '"","","","","","","箱号","FBATEST01U000001"',
            '"","","","","","","包装箱名称","P1 - B1"',
            '"","","","","","","包装箱重量（kg）：","10"',
            '"","","","","","","包装箱长度（cm）：","10"',
            '"","","","","","","包装箱宽度（cm）：","10"',
            '"","","","","","","包装箱高度（cm）：","10"',
        ]),
        encoding="utf-8",
    )
    from fba_tool.shipment_parser import parse_csv_shipment, snapshot_box_id

    ship = parse_csv_shipment(csv_path.read_bytes(), file_name=csv_path.name)
    assert list(ship.box_specs["FBA箱号"]) == ["FBATEST01U000001"]
    assert list(ship.box_specs["箱名"]) == ["P1 - B1"]
    assert ship.box_fba_ids[1] == "FBATEST01U000001"
    assert ship.box_names[1] == "P1 - B1"
    spec = ship.box_specs.iloc[0]
    assert snapshot_box_id(spec, ship.box_fba_ids) == "FBATEST01U000001"
    # 规格列若仍被包装箱名称盖住，选择函数也要回退到真箱唛。
    poisoned = dict(spec)
    poisoned["FBA箱号"] = "P1 - B1"
    assert snapshot_box_id(poisoned, ship.box_fba_ids) == "FBATEST01U000001"
    assert snapshot_box_id({"箱号": 1, "FBA箱号": "P1 - B1"}, {}) == "P1 - B1"

    summary = summarize_batch13(root)
    assert summary["matched_rows"] == 1
    assert summary["box_total"] == Decimal("10.00")
    from tests.smoke.test_box_realdata_smoke import _product_compare

    product = _product_compare(monkeypatch, tmp_path, summary)
    assert product["rows"] == 1
    assert product["box_total"] == summary["box_total"]
    assert product["box_total"] != Decimal("0.00")


def test_batch13_name_in_box_column_still_reconciles(monkeypatch, tmp_path):
    """第 13 批：箱号列是箱名，真箱唛在另一列，而且 U 后缀不等于 B 号。box_total 不能是 0。"""
    root = tmp_path / "real"
    measure = root / "batches" / "第13批" / "九方确认账单文件"
    measure.mkdir(parents=True)
    mark = "FBATEST13U000007"
    _book(measure / "九方.xlsx", [
        ["外箱号", "运单号", "单箱实重", "长", "宽", "高"],
        [mark, "WBTEST13", 20, 40, 40, 40],
        ["入库计费重", 20],
    ])
    csv_path = root / "batches" / "第13批" / "ship.csv"
    csv_path.write_text(
        "\n".join([
            '"货件编号","FBATEST13"',
            '"货件名称","S13"',
            '"配送地址","STEP45VILLE, ZZ"',
            '"箱子数量","1"',
            "",
            '"单件商品（1 箱）"',
            '"SKU","商品名称","ASIN","FNSKU","状况","预处理类型","商品总数","箱子 1 的商品数量"',
            '"S13-SKU","rod","B0S13TEST1","X00TESTS13","新品","无","1","1"',
            "",
            '"","","","","","","箱号","P1 - B34"',
            '"FBA箱号","","FBATEST13U000007"',
            '"","","","","","","包装箱重量（kg）：","10"',
            '"","","","","","","包装箱长度（cm）：","10"',
            '"","","","","","","包装箱宽度（cm）：","10"',
            '"","","","","","","包装箱高度（cm）：","10"',
        ]),
        encoding="utf-8",
    )
    from fba_tool.shipment_parser import parse_csv_shipment, snapshot_box_id

    ship = parse_csv_shipment(csv_path.read_bytes(), file_name=csv_path.name)
    assert list(ship.box_specs["FBA箱号"]) == [mark]
    assert list(ship.box_specs["箱名"]) == ["P1 - B34"]
    assert ship.box_fba_ids == {34: mark}
    assert ship.box_names == {34: "P1 - B34"}
    assert "P1 - B34" not in ship.box_fba_ids.values()
    assert snapshot_box_id(ship.box_specs.iloc[0], ship.box_fba_ids) == mark

    summary = summarize_batch13(root)
    assert summary["matched_rows"] == 1
    assert summary["box_total"] == Decimal("10.00")
    assert summary["box_total"] != Decimal("0.00")
    from tests.smoke.test_box_realdata_smoke import _product_compare

    product = _product_compare(monkeypatch, tmp_path, summary)
    assert product["rows"] == 1
    assert product["box_total"] == summary["box_total"]
    assert product["box_total"] != Decimal("0.00")


def _sta_named_box_csv(name_before_id: bool) -> bytes:
    """箱 34：真箱唛和 STA 箱名各一行。两种先后都要保住箱唛。"""
    mark = '"","","","","","","箱号","FBATEST34U000034"'
    name = '"","","","","","","包装箱名称","P1 - B34"'
    labels = [name, mark] if name_before_id else [mark, name]
    return "\n".join([
        '"货件编号","FBATEST34"',
        '"货件名称","S34"',
        '"配送地址","STEP45VILLE, ZZ"',
        '"箱子数量","34"',
        "",
        '"单件商品（1 箱）"',
        '"SKU","商品名称","ASIN","FNSKU","状况","预处理类型","商品总数","箱子 1 的商品数量"',
        '"S34-SKU","rod","B0S34TEST1","X00TESTS34","新品","无","1","1"',
        "",
        *labels,
        '"","","","","","","包装箱重量（kg）：","10"',
        '"","","","","","","包装箱长度（cm）：","10"',
        '"","","","","","","包装箱宽度（cm）：","10"',
        '"","","","","","","包装箱高度（cm）：","10"',
    ]).encode("utf-8")


@pytest.mark.parametrize("name_before_id", [False, True])
def test_sta_box_name_stays_off_the_fba_box_id(name_before_id):
    """包装箱名称不能写进 FBA 箱号。箱规对账、箱贴、快照都按原箱唛匹配。"""
    from fba_tool.box_label_mapping import collect_amazon_boxes
    from fba_tool.shipment_cross_check import _declared_specs_by_box
    from fba_tool.shipment_parser import PdfShipment, parse_csv_shipment, snapshot_box_id
    from fba_tool.shipment_serialize import csv_shipment_from_dict, csv_shipment_to_dict
    from fba_tool.shipment_validator import ShipmentPair

    mark, name = "FBATEST34U000034", "P1 - B34"
    ship = parse_csv_shipment(_sta_named_box_csv(name_before_id), file_name="box34.csv")
    assert ship.column_to_box
    assert 34 in ship.column_to_box.values()
    assert list(ship.box_specs["FBA箱号"]) == [mark]
    assert list(ship.box_specs["箱名"]) == [name]
    assert ship.box_fba_ids == {34: mark}
    assert ship.box_names == {34: name}
    assert name not in ship.box_fba_ids.values()
    spec = ship.box_specs.iloc[0]
    assert snapshot_box_id(spec, ship.box_fba_ids) == mark

    pair = ShipmentPair(ship.shipment_id, ship.warehouse_code, ship, PdfShipment(ship.shipment_id, 0))
    declared = _declared_specs_by_box([pair])
    assert declared[(ship.shipment_id, 34)]["fba_box_id"] == mark
    boxes = collect_amazon_boxes([pair])
    assert [(box.amazon_box_no, box.fba_box_id) for box in boxes] == [(34, mark)]

    restored = csv_shipment_from_dict(csv_shipment_to_dict(ship))
    assert restored is not None
    assert restored.box_fba_ids[34] == mark
    assert restored.box_names[34] == name
    assert snapshot_box_id(restored.box_specs.iloc[0], restored.box_fba_ids) == mark


def test_entry_sheet_sku_cl2_is_not_a_net_source(tmp_path):
    batch = tmp_path / "batches" / "第13批" / "发给工厂"
    _book_path = batch / "发货录入样表.xlsx"
    _book_path.parent.mkdir(parents=True)
    _book(_book_path, [
        ["SKU简称", "发货总数", "单箱毛重", "空纸箱重(kg)"],
        ["WIDGET-CL2", 32, 264, 0.3],
    ])
    with pytest.raises(LayoutMissing, match="发货表"):
        cl2_net(tmp_path)


def test_missing_tare_uses_product_fallback(tmp_path):
    batch = tmp_path / "batches" / "第13批"
    _shipping(batch / "发给工厂" / "发货表.xlsx", "1-18", "19-32")
    got = cl2_net(tmp_path)
    assert got["tare"] == Decimal("0.2")
    assert got["net"] == Decimal("257.6")
    assert "0.2" in got["detail"]
