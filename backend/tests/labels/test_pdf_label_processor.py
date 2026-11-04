"""PDF 标签智能裁剪测试。"""
from io import BytesIO

import fitz

from fba_tool.pdf_label_processor import (
    PDFLabelProcessor,
    ProcessOptions,
    create_separator_banner_page,
    mm_to_pt,
    parse_process_options,
    resolve_size,
    thermal_labels_pdf,
)


def _single_label_a4_pdf() -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=mm_to_pt(210), height=mm_to_pt(297))
    rect = fitz.Rect(mm_to_pt(40), mm_to_pt(50), mm_to_pt(160), mm_to_pt(150))
    page.draw_rect(rect, color=(0, 0, 0), width=2)
    page.insert_text((rect.x0 + 10, rect.y0 + 30), "FBA TEST LABEL", fontsize=14)
    data = doc.tobytes()
    doc.close()
    return data


def _grid_labels_pdf(cols: int = 4, rows: int = 6) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=mm_to_pt(210), height=mm_to_pt(297))
    margin_x, margin_y = mm_to_pt(8), mm_to_pt(10)
    usable_w = page.rect.width - 2 * margin_x
    usable_h = page.rect.height - 2 * margin_y
    cell_w = usable_w / cols
    cell_h = usable_h / rows
    for r in range(rows):
        for c in range(cols):
            x0 = margin_x + c * cell_w + mm_to_pt(4)
            y0 = margin_y + r * cell_h + mm_to_pt(4)
            x1 = margin_x + (c + 1) * cell_w - mm_to_pt(4)
            y1 = margin_y + (r + 1) * cell_h - mm_to_pt(4)
            page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=(0, 0, 0), width=1)
            page.insert_text((x0 + 4, y0 + 12), f"L{r * cols + c + 1}", fontsize=8)
    data = doc.tobytes()
    doc.close()
    return data


def _page_size_pt(pdf_bytes: bytes) -> tuple[float, float]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        rect = doc[0].rect
        return rect.width, rect.height
    finally:
        doc.close()


def test_single_label_output_size():
    src = _single_label_a4_pdf()
    out = thermal_labels_pdf([src], "carton_100x100")
    doc = fitz.open(stream=out, filetype="pdf")
    try:
        assert doc.page_count >= 1
        w, h = doc[0].rect.width, doc[0].rect.height
        target = resolve_size("carton_100x100")
        assert abs(w - target.width_pt) < 1
        assert abs(h - target.height_pt) < 1
    finally:
        doc.close()


def test_grid_splits_into_multiple_pages():
    src = _grid_labels_pdf(4, 6)
    doc = fitz.open(stream=src, filetype="pdf")
    try:
        proc = PDFLabelProcessor()
        boxes = proc._detect_all_labels(doc)
    finally:
        doc.close()
    assert len(boxes) >= 20

    out = thermal_labels_pdf([src], "product_60x40")
    doc = fitz.open(stream=out, filetype="pdf")
    try:
        assert doc.page_count >= 20
        target = resolve_size("product_60x40")
        w, h = doc[0].rect.width, doc[0].rect.height
        assert abs(w - target.width_pt) < 1
        assert abs(h - target.height_pt) < 1
    finally:
        doc.close()


def test_process_many_merges_files():
    a = _single_label_a4_pdf()
    b = _single_label_a4_pdf()
    out = thermal_labels_pdf([a, b], "carton_100x100")
    doc = fitz.open(stream=out, filetype="pdf")
    try:
        assert doc.page_count >= 2
    finally:
        doc.close()


def test_parse_process_options_defaults():
    opt = parse_process_options({})
    assert opt.padding_mm == 2.5
    assert opt.margin_ratio == 0.025
    assert opt.auto_rotate is True
    assert opt.insert_separator is True
    assert opt.carrier_adaptive is False
    assert opt.ignore_top_mm == 0.0
    assert opt.ignore_bottom_mm == 0.0
    assert opt.detect_dpi == 120
    assert opt.custom_text is None


def test_parse_process_options_custom_text():
    opt = parse_process_options({"custom_text": "  MADE IN CHINA  "})
    assert opt.custom_text == "MADE IN CHINA"
    assert parse_process_options({"custom_text": "   "}).custom_text is None
    long_text = "A" * 100
    assert len(parse_process_options({"custom_text": long_text}).custom_text or "") == 80


def test_custom_text_overlay_on_output():
    src = _single_label_a4_pdf()
    out = thermal_labels_pdf(
        [src],
        "carton_100x100",
        options=ProcessOptions(custom_text="MADE IN CHINA"),
    )
    doc = fitz.open(stream=out, filetype="pdf")
    try:
        text = doc[0].get_text()
        assert "MADE IN CHINA" in text
    finally:
        doc.close()


def test_custom_text_empty_skips_overlay():
    src = _single_label_a4_pdf()
    out_with = thermal_labels_pdf(
        [src],
        "carton_100x100",
        options=ProcessOptions(custom_text="MADE IN CHINA"),
    )
    out_without = thermal_labels_pdf([src], "carton_100x100")
    doc_with = fitz.open(stream=out_with, filetype="pdf")
    doc_without = fitz.open(stream=out_without, filetype="pdf")
    try:
        assert "MADE IN CHINA" in doc_with[0].get_text()
        assert "MADE IN CHINA" not in doc_without[0].get_text()
    finally:
        doc_with.close()
        doc_without.close()


def test_parse_process_options_clamps_invalid_dpi():
    opt = parse_process_options({"detect_dpi": 999, "padding_mm": -1})
    assert opt.detect_dpi == 120
    assert opt.padding_mm == 2.5


def test_ignore_top_region_excludes_header_ink():
    doc = fitz.open()
    page = doc.new_page(width=mm_to_pt(210), height=mm_to_pt(297))
    header = fitz.Rect(mm_to_pt(10), mm_to_pt(5), mm_to_pt(200), mm_to_pt(20))
    label = fitz.Rect(mm_to_pt(40), mm_to_pt(50), mm_to_pt(160), mm_to_pt(150))
    page.draw_rect(header, color=(0, 0, 0), width=2)
    page.draw_rect(label, color=(0, 0, 0), width=2)
    page.insert_text((header.x0 + 4, header.y0 + 12), "FULFILLMENT HEADER", fontsize=10)
    page.insert_text((label.x0 + 10, label.y0 + 30), "FBA TEST LABEL", fontsize=14)
    src = doc.tobytes()
    doc.close()

    proc_default = PDFLabelProcessor()
    doc = fitz.open(stream=src, filetype="pdf")
    try:
        boxes_default = proc_default._detect_all_labels(doc)
    finally:
        doc.close()
    assert len(boxes_default) >= 2

    proc_ignore = PDFLabelProcessor(
        ProcessOptions(ignore_top_mm=25.0),
    )
    doc = fitz.open(stream=src, filetype="pdf")
    try:
        boxes_ignore = proc_ignore._detect_all_labels(doc)
    finally:
        doc.close()
    assert len(boxes_ignore) == 1




def test_quiet_zone_margin_spec():
    # ANSI/ISO 15417 & Amazon 6.35mm quiet zone
    opt = parse_process_options({})
    assert opt.padding_mm == 2.5
    assert opt.margin_ratio == 0.025
    target = resolve_size("carton_100x100")
    # Margin on each side is 100mm * 0.025 = 2.5mm
    margin_mm = target.width_mm * opt.margin_ratio
    total_clearance_mm = margin_mm + opt.padding_mm
    assert total_clearance_mm >= 5.0, f"Total quiet zone clearance {total_clearance_mm}mm must be >= 5.0mm"


def _landscape_product_label_pdf(width_mm: float = 70.0, height_mm: float = 36.0) -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=mm_to_pt(210), height=mm_to_pt(297)) # A4
    rect = fitz.Rect(mm_to_pt(20), mm_to_pt(20), mm_to_pt(20 + width_mm), mm_to_pt(20 + height_mm))
    page.draw_rect(rect, color=(0, 0, 0), width=1.5)
    page.insert_text((rect.x0 + 10, rect.y0 + 25), "FNSKU: X001ABCD", fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def test_auto_rotate_landscape_label_into_portrait():
    # 70x36mm landscape label placed into 40x60mm portrait canvas
    src = _landscape_product_label_pdf(70.0, 36.0)

    # 1. With auto_rotate=True (default)
    out_rot = thermal_labels_pdf([src], width_mm=40.0, height_mm=60.0, options=ProcessOptions(auto_rotate=True))
    doc_rot = fitz.open(stream=out_rot, filetype="pdf")
    assert doc_rot.page_count >= 1
    p_rot = doc_rot[0]
    # Verify page dimensions
    assert abs(p_rot.rect.width - mm_to_pt(40.0)) < 1.0
    assert abs(p_rot.rect.height - mm_to_pt(60.0)) < 1.0
    text_rot = p_rot.get_text()
    assert "FNSKU: X001ABCD" in text_rot
    doc_rot.close()

    # 2. With auto_rotate=False
    out_norot = thermal_labels_pdf([src], width_mm=40.0, height_mm=60.0, options=ProcessOptions(auto_rotate=False))
    doc_norot = fitz.open(stream=out_norot, filetype="pdf")
    assert doc_norot.page_count >= 1
    doc_norot.close()


def test_shipment_separator_banner_page_generation():
    size = resolve_size("carton_100x100")
    banner_pdf = create_separator_banner_page(
        size=size,
        shipment_id="FBA18XYZ789",
        warehouse="ONT8",
        box_count=45,
        ticket_label="第一票",
    )
    doc = fitz.open(stream=banner_pdf, filetype="pdf")
    try:
        assert doc.page_count == 1
        page = doc[0]
        text = page.get_text()
        assert "FBA18XYZ789" in text
        assert "ONT8" in text
        assert "45" in text
    finally:
        doc.close()


def test_multi_shipment_separator_insertion():
    pdf1 = _single_label_a4_pdf()
    pdf2 = _single_label_a4_pdf()
    shipments_meta = [
        {"shipment_id": "FBA18ONT8_001", "warehouse": "ONT8", "carton_count": 1},
        {"shipment_id": "FBA18LAX9_002", "warehouse": "LAX9", "carton_count": 1},
    ]
    out = thermal_labels_pdf(
        [pdf1, pdf2],
        "carton_100x100",
        shipments_meta=shipments_meta,
        options=ProcessOptions(insert_separator=True),
    )
    doc = fitz.open(stream=out, filetype="pdf")
    try:
        # 2 shipment labels + 2 separator banner pages = 4 pages
        assert doc.page_count == 4
        all_text = "".join(doc[i].get_text() for i in range(doc.page_count))
        assert "ONT8" in all_text
        assert "LAX9" in all_text
    finally:
        doc.close()


def _carrier_ups_4x6_pdf() -> bytes:
    doc = fitz.open()
    # 4x6 inches: 101.6 x 152.4 mm (288 x 432 pt)
    page = doc.new_page(width=mm_to_pt(101.6), height=mm_to_pt(152.4))
    rect = fitz.Rect(mm_to_pt(5), mm_to_pt(5), mm_to_pt(96.6), mm_to_pt(147.4))
    page.draw_rect(rect, color=(0, 0, 0), width=1)
    page.insert_text((rect.x0 + 10, rect.y0 + 30), "UPS GROUND", fontsize=14)
    page.insert_text((rect.x0 + 10, rect.y0 + 60), "TRACKING #: 1Z 999 999 99 9999 9999", fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


def test_carrier_4x6_aspect_ratio_fidelity():
    src = _carrier_ups_4x6_pdf()

    # 1. Strict isometric proportion (never squashed non-uniformly)
    out_std = thermal_labels_pdf([src], "carton_100x100", options=ProcessOptions(carrier_adaptive=False))
    doc_std = fitz.open(stream=out_std, filetype="pdf")
    try:
        assert doc_std.page_count >= 1
        assert "UPS GROUND" in doc_std[0].get_text()
    finally:
        doc_std.close()

    # 2. Carrier adaptive mode routes 4x6 to 100x150mm canvas
    out_adap = thermal_labels_pdf([src], "carton_100x100", options=ProcessOptions(carrier_adaptive=True))
    doc_adap = fitz.open(stream=out_adap, filetype="pdf")
    try:
        assert doc_adap.page_count >= 1
        w, h = doc_adap[0].rect.width, doc_adap[0].rect.height
        # 100x150mm is 283.46 x 425.20 pt
        target_150 = resolve_size("product_100x150")
        assert abs(w - target_150.width_pt) < 1.0
        assert abs(h - target_150.height_pt) < 1.0
        assert "UPS GROUND" in doc_adap[0].get_text()
    finally:
        doc_adap.close()


def test_detect_barcode_x_bounds():
    import numpy as np
    from fba_tool.pdf_label_processor import detect_barcode_x_bounds

    # Synthetic label mask: 100 x 200
    mask = np.zeros((100, 200), dtype=bool)
    # Simulate barcode in rows 15-45, columns 60-140 (alternating bars)
    for c in range(60, 140, 2):
        mask[15:45, c] = True

    bounds = detect_barcode_x_bounds(mask)
    assert bounds is not None
    assert bounds[0] == 60
    assert bounds[1] == 138

    # Non-barcode mask (plain text with low transitions)
    text_mask = np.zeros((100, 200), dtype=bool)
    text_mask[10:20, 20:50] = True
    assert detect_barcode_x_bounds(text_mask) is None


def test_barcode_optical_centering_with_asymmetric_title():
    import numpy as np
    from fba_tool.pdf_label_processor import (
        PDFLabelProcessor, ProcessOptions, resolve_size, mm_to_pt
    )

    doc = fitz.open()
    page = doc.new_page(width=mm_to_pt(210), height=mm_to_pt(297))

    # Cell: Barcode from x=70 to x=150 (width=80, center=110)
    # Draw vertical stripes for barcode
    for x in range(70, 150, 3):
        page.draw_rect(fitz.Rect(mm_to_pt(x), mm_to_pt(50), mm_to_pt(x + 1), mm_to_pt(70)), color=(0,0,0), fill=(0,0,0))

    # Title is left-aligned: from x=30 to x=80 (asymmetric, pulls bbox left)
    page.draw_rect(fitz.Rect(mm_to_pt(30), mm_to_pt(75), mm_to_pt(80), mm_to_pt(85)), color=(0,0,0), fill=(0,0,0))
    src_bytes = doc.tobytes()
    doc.close()

    proc = PDFLabelProcessor(ProcessOptions(center_barcode=True, center_content=True))
    size = resolve_size("product_60x40")
    out_pdf = proc.process(src_bytes, size)

    out_doc = fitz.open(stream=out_pdf, filetype="pdf")
    try:
        assert out_doc.page_count == 1
        out_page = out_doc[0]
        # Verify page width is 60mm in points
        assert abs(out_page.rect.width - size.width_pt) < 1.0
    finally:
        out_doc.close()


def test_bottom_custom_text_centered_baseline():
    from fba_tool.pdf_label_processor import (
        PDFLabelProcessor, ProcessOptions, resolve_size, BOTTOM_TEXT_BAND_MM, mm_to_pt
    )

    src = _single_label_a4_pdf()
    proc = PDFLabelProcessor(ProcessOptions(custom_text="MADE IN CHINA", center_content=True))
    size = resolve_size("product_60x40")
    out = proc.process(src, size)
    doc = fitz.open(stream=out, filetype="pdf")
    try:
        assert doc.page_count == 1
        page = doc[0]
        text_page = page.get_text("blocks")
        # Ensure MADE IN CHINA is present
        found = False
        for b in text_page:
            if "MADE IN CHINA" in b[4]:
                found = True
                # Check that horizontal center of text block is close to page center (within 5pt)
                text_center_x = (b[0] + b[2]) / 2.0
                assert abs(text_center_x - (page.rect.width / 2.0)) < 5.0
                # Check vertical position: should be within the bottom band
                band_pt = mm_to_pt(BOTTOM_TEXT_BAND_MM)
                assert b[1] > page.rect.height - band_pt * 2.0
        assert found
    finally:
        doc.close()

if __name__ == "__main__":
    test_single_label_output_size()
    test_grid_splits_into_multiple_pages()
    test_process_many_merges_files()
    test_parse_process_options_defaults()
    test_parse_process_options_custom_text()
    test_custom_text_overlay_on_output()
    test_custom_text_empty_skips_overlay()
    test_parse_process_options_clamps_invalid_dpi()
    test_ignore_top_region_excludes_header_ink()
    print("ALL OK")
