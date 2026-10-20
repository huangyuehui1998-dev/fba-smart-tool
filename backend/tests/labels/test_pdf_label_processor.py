"""PDF 标签智能裁剪测试。"""
from io import BytesIO

import fitz

from fba_tool.pdf_label_processor import (
    PDFLabelProcessor,
    ProcessOptions,
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
    assert opt.padding_mm == 1.0
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
    assert opt.padding_mm == 1.0


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
