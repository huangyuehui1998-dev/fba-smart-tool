"""货代档案与琪珞工作流装配测试。"""
from pathlib import Path

from fba_tool.forwarder_registry import get_forwarder, list_forwarders
from fba_tool.invoice_table import detect_invoice_table_layout
from fba_tool.invoice_workflow_fill import build_workflow_bundle
from fba_tool.xlsx_io import load_workbook_fast
from fba_tool.invoice_automation import load_invoice_config


def test_forwarders_include_qiluo():
    items = list_forwarders()
    ids = {f.id for f in items}
    assert "qiluo" in ids
    q = get_forwarder("qiluo")
    assert q.name == "琪珞国际"


def test_workflow_bundle_reads_step1_and_forwarder():
    bundle = build_workflow_bundle(
        {
            "input_rows": [{"SKU简称": "ABC", "单箱装量": 4, "单个重量(kg)": 1.2}],
            "forwarder": [{"SKU": "ABC", "箱序号": "1,2", "单件实重(kg)": 0.5}],
        }
    )
    ctx = bundle.by_sku["ABC"]
    assert ctx.per_box == 4
    assert ctx.box_seq == "1-2"


def test_qiluo_template_detects_without_sku_column():
    tpl = Path(__file__).resolve().parents[2] / "templates" / "forwarders" / "qiluo.xlsx"
    wb = load_workbook_fast(tpl.read_bytes())
    layout = detect_invoice_table_layout(wb, cfg=load_invoice_config())
    assert layout is not None
    assert "fba_id" in layout.columns
    assert "po_number" in layout.columns
