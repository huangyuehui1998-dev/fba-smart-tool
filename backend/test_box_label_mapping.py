"""本地箱号 ↔ FBA 箱唛映射测试。"""
from pathlib import Path

import pandas as pd

from fba_tool.box_label_mapping import (
    build_factory_long_with_mapping,
    format_local_box_label,
    local_box_contents,
    match_local_to_amazon_boxes,
)
from fba_tool.fba_parser import simplify_sku
from fba_tool.shipment_parser import parse_csv_shipment
from fba_tool.shipment_validator import validate_shipments


def _editor_from_csv(csv_bytes: bytes) -> pd.DataFrame:
    ship = parse_csv_shipment(csv_bytes)
    rows = []
    local_box = 1
    for amazon_box_no in sorted(ship.box_data.keys()):
        for sku, qty in ship.box_data[amazon_box_no].items():
            if qty > 0:
                rows.append(
                    {
                        "箱号": local_box,
                        "来源": "测试",
                        "SKU简称": simplify_sku(sku),
                        "数量": qty,
                    }
                )
        local_box += 1
    return pd.DataFrame(rows)


def test_format_local_box_label():
    assert format_local_box_label(1) == "Box-01"
    assert format_local_box_label(10) == "Box-10"


def test_local_box_contents():
    editor = pd.DataFrame(
        [
            {"箱号": 1, "来源": "整箱", "SKU简称": "GREY-4pcs", "数量": 3},
            {"箱号": 1, "来源": "整箱", "SKU简称": "GREY-2pcs", "数量": 6},
            {"箱号": 2, "来源": "整箱", "SKU简称": "ZHONG-4pcs", "数量": 3},
        ]
    )
    contents = local_box_contents(editor)
    assert contents[1]["GREY-4pcs"] == 3
    assert contents[1]["GREY-2pcs"] == 6
    assert contents[2]["ZHONG-4pcs"] == 3


def test_mapping_with_template_csv():
    csv_path = Path("templates/亚马逊FBA表1.csv")
    if not csv_path.exists():
        return
    tpl = Path("templates")
    # S8 D12：同一货件重复上传现在是硬错误；templates 里“亚马逊FBA表.csv”和“表1.csv”是同一票（FBA19F4BDYRN），
    # 产品信息表也不是货件 CSV，这里只传 表1–5
    csv_payload = [(f.name, f.read_bytes()) for f in sorted(tpl.glob("亚马逊FBA表[1-9].csv"))]
    pdf_payload = [(f.name, f.read_bytes()) for f in sorted(tpl.glob("*.pdf"))]
    if not pdf_payload:
        return

    editor_df = _editor_from_csv(csv_path.read_bytes())
    result = validate_shipments(csv_payload, pdf_payload)
    assert result.ok, result.errors

    mapping = match_local_to_amazon_boxes(editor_df, result.pairs)
    assert mapping.ok, mapping.errors
    assert len(mapping.matches) == len(local_box_contents(editor_df))
    assert all(m.fba_box_id for m in mapping.matches)

    factory = build_factory_long_with_mapping(editor_df, mapping)
    assert "本地箱号" in factory.columns
    assert "FBA箱号" in factory.columns
    assert "目的仓" in factory.columns
    assert "贴标说明" in factory.columns
    assert factory["FBA箱号"].astype(str).str.startswith("FBA").all()


if __name__ == "__main__":
    test_format_local_box_label()
    test_local_box_contents()
    test_mapping_with_template_csv()
    print("ALL OK")
