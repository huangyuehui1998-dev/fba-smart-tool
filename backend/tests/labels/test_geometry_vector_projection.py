"""几何变换与矢量投影开源对标测试 (Geometry & Vector Projection OSS Test Suite)。"""
import fitz
import pytest

from fba_tool.pdf_label_processor import (
    PDFLabelProcessor,
    ProcessOptions,
    mm_to_pt,
    resolve_size,
    thermal_labels_pdf,
)


def _make_rotated_label_pdf(angle: int = 90) -> bytes:
    """生成带有指定原生旋转 /Rotate 的测试 PDF 标签。"""
    doc = fitz.open()
    page = doc.new_page(width=mm_to_pt(210), height=mm_to_pt(297))
    rect = fitz.Rect(mm_to_pt(40), mm_to_pt(50), mm_to_pt(160), mm_to_pt(150))
    page.draw_rect(rect, color=(0, 0, 0), width=2)
    page.insert_text((rect.x0 + 10, rect.y0 + 30), f"FBA ROT_{angle} LABEL", fontsize=14)
    page.set_rotation(angle)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_native_rotation_preserves_vector_content(angle: int):
    """验证 /Rotate 0/90/180/270 原生旋转页面矢量剪裁无空白页缺陷。"""
    src = _make_rotated_label_pdf(angle)
    out = thermal_labels_pdf([src], "carton_100x100")
    doc = fitz.open(stream=out, filetype="pdf")
    try:
        assert doc.page_count >= 1
        page = doc[0]
        text = page.get_text()
        # 必须提取出完整的文字，杜绝空白页
        assert f"FBA ROT_{angle} LABEL" in text
    finally:
        doc.close()


def test_bottom_text_isolation_across_all_sizes():
    """验证底栏文本垂直居中公式对原标的绝对物理隔离性（无下沉压印）。"""
    src = _make_rotated_label_pdf(0)
    for size_name in ["product_60x40", "carton_100x100", "product_100x150"]:
        out = thermal_labels_pdf(
            [src],
            size_name,
            options=ProcessOptions(custom_text="FBA-ISOLATION-CHECK"),
        )
        doc = fitz.open(stream=out, filetype="pdf")
        try:
            page = doc[0]
            text = page.get_text()
            assert "FBA-ISOLATION-CHECK" in text
            assert "FBA ROT_0 LABEL" in text
            # 验证文字块位置在底部安全区（距离底部 < 6mm）
            blocks = page.get_text("blocks")
            custom_block = [b for b in blocks if "FBA-ISOLATION-CHECK" in b[4]][0]
            assert custom_block[3] >= page.rect.height - mm_to_pt(5.0)
        finally:
            doc.close()


def test_cjk_font_rendering_and_dynamic_scaling():
    """验证内置 CJK 字体映射方案 (china-s) 及超长中文字符串平滑动态缩放。"""
    src = _make_rotated_label_pdf(0)
    # 测试中文字符与长文本
    cjk_text = "FBA箱标 - 红色大号 混装 50件 - 超长仓位标识编码-ONT8-AMZ-BULK"
    out = thermal_labels_pdf(
        [src],
        "product_60x40",
        options=ProcessOptions(custom_text=cjk_text),
    )
    doc = fitz.open(stream=out, filetype="pdf")
    try:
        page = doc[0]
        text = page.get_text()
        assert "FBA箱标" in text
        assert "红色大号" in text
        # 验证文本完全位于页面可视宽度内（无横向溢出）
        blocks = page.get_text("blocks")
        cjk_block = [b for b in blocks if "FBA箱标" in b[4]][0]
        assert cjk_block[0] >= 0.0
        assert cjk_block[2] <= page.rect.width
    finally:
        doc.close()
