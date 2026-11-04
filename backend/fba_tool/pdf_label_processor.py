"""通用 PDF 标签智能裁剪 / 重排引擎。

设计目标：
  - 不依赖写死坐标，纯内容驱动（Bounding-Box 墨迹检测）。
  - 支持一页多个独立标签（如 24-up 产品贴）自动切分。
  - 等比居中投影到指定物理尺寸（mm）新页面，矢量无损。
  - 多文件 / 多页并行处理，充分利用 CPU。
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from fba_tool.box_label_filename import parse_box_label_pdf_name
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

class _LazyModule:
    """推迟导入。PyMuPDF 会在 import 时加载版面模型，不能放进进程启动。"""

    def __init__(self, name: str) -> None:
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_mod", None)

    def _load(self):
        mod = object.__getattribute__(self, "_mod")
        if mod is None:
            import importlib

            mod = importlib.import_module(object.__getattribute__(self, "_name"))
            object.__setattr__(self, "_mod", mod)
        return mod

    def __getattr__(self, item: str):
        return getattr(self._load(), item)


fitz = _LazyModule("fitz")
np = _LazyModule("numpy")

_scipy_state: Any = None


def _scipy_ndimage():
    global _scipy_state
    if _scipy_state is None:
        try:
            from scipy import ndimage as ndi

            _scipy_state = ndi
        except ImportError:  # pragma: no cover
            _scipy_state = False
    return _scipy_state or None

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
ALLOWED_DETECT_DPIS = (120, 200, 300)
BOTTOM_TEXT_BAND_MM = 4.0
MAX_CUSTOM_TEXT_LEN = 80
MAX_PHYSICAL_PAGE_PT = 1700.0  # ? 600mm???????????????
MAX_RASTER_DIM_PX = 4096      # ? OOM ???????????

ProgressFn = Callable[[int, str], None]


def mm_to_pt(mm: float) -> float:
    """毫米 → PDF 点（pt）。"""
    return mm / MM_PER_INCH * PT_PER_INCH


def default_worker_count(task_count: int) -> int:
    """并行 worker 数：尽量占满 CPU，且不超过任务数。"""
    cpus = os.cpu_count() or 4
    return max(1, min(task_count, cpus))


def resolve_worker_count(opt: ProcessOptions, task_count: int) -> int:
    if opt.max_workers > 0:
        return max(1, min(opt.max_workers, task_count))
    return default_worker_count(task_count)


@dataclass(frozen=True)
class LabelSize:
    key: str
    name: str
    width_mm: float
    height_mm: float

    @property
    def width_pt(self) -> float:
        return mm_to_pt(self.width_mm)

    @property
    def height_pt(self) -> float:
        return mm_to_pt(self.height_mm)


PRESET_SIZES: Dict[str, LabelSize] = {
    "carton_100x100": LabelSize("carton_100x100", "外箱标 100×100mm", 100.0, 100.0),
    "product_60x40": LabelSize("product_60x40", "产品标 60×40mm", 60.0, 40.0),
    "product_100x150": LabelSize("product_100x150", "面单 100×150mm", 100.0, 150.0),
    "product_40x30": LabelSize("product_40x30", "小标 40×30mm", 40.0, 30.0),
}


@dataclass(frozen=True)
class ProcessOptions:
    detect_dpi: int = 120
    ink_threshold: int = 248
    merge_gap_mm: float = 2.0
    min_label_mm: float = 12.0
    padding_mm: float = 2.5
    margin_ratio: float = 0.025
    max_workers: int = 0  # 0 = auto
    ignore_top_mm: float = 0.0
    ignore_bottom_mm: float = 0.0
    custom_text: Optional[str] = None
    auto_rotate: bool = True
    insert_separator: bool = True
    carrier_adaptive: bool = False
    center_barcode: bool = True
    center_content: bool = True


def _clamp_nonneg_float(value: Any, default: float, *, max_val: float = 50.0) -> float:
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return default
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if not (n >= 0):
        return default
    return min(n, max_val)


def _parse_detect_dpi(value: Any, default: int = 120) -> int:
    if value is None or (isinstance(value, str) and not str(value).strip()):
        return default
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return default
    return n if n in ALLOWED_DETECT_DPIS else default


def _parse_custom_text(value: Any) -> Optional[str]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:MAX_CUSTOM_TEXT_LEN]


def _bottom_text_font_size(height_mm: float) -> float:
    return max(6.0, min(10.0, height_mm * 0.08))


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return default


def parse_process_options(
    source: Mapping[str, Any] | None = None,
    *,
    base: ProcessOptions | None = None,
    padding_mm: Any = None,
    margin_ratio: Any = None,
    ignore_top_mm: Any = None,
    ignore_bottom_mm: Any = None,
    detect_dpi: Any = None,
    custom_text: Any = None,
    auto_rotate: Any = None,
    insert_separator: Any = None,
    carrier_adaptive: Any = None,
    center_barcode: Any = None,
    center_content: Any = None,
) -> ProcessOptions:
    """从 dict / Form 字段统一解析 ProcessOptions。"""
    opt = base or ProcessOptions()
    src = source or {}
    return replace(
        opt,
        padding_mm=_clamp_nonneg_float(
            padding_mm if padding_mm is not None else src.get("padding_mm"),
            opt.padding_mm,
        ),
        margin_ratio=_clamp_nonneg_float(
            margin_ratio if margin_ratio is not None else src.get("margin_ratio"),
            opt.margin_ratio,
            max_val=0.25,
        ),
        ignore_top_mm=_clamp_nonneg_float(
            ignore_top_mm if ignore_top_mm is not None else src.get("ignore_top_mm"),
            opt.ignore_top_mm,
        ),
        ignore_bottom_mm=_clamp_nonneg_float(
            ignore_bottom_mm if ignore_bottom_mm is not None else src.get("ignore_bottom_mm"),
            opt.ignore_bottom_mm,
        ),
        detect_dpi=_parse_detect_dpi(
            detect_dpi if detect_dpi is not None else src.get("detect_dpi"),
            opt.detect_dpi,
        ),
        custom_text=_parse_custom_text(
            custom_text if custom_text is not None else src.get("custom_text"),
        ),
        auto_rotate=_parse_bool(
            auto_rotate if auto_rotate is not None else src.get("auto_rotate"),
            opt.auto_rotate,
        ),
        insert_separator=_parse_bool(
            insert_separator if insert_separator is not None else src.get("insert_separator"),
            opt.insert_separator,
        ),
        carrier_adaptive=_parse_bool(
            carrier_adaptive if carrier_adaptive is not None else src.get("carrier_adaptive"),
            opt.carrier_adaptive,
        ),
        center_barcode=_parse_bool(
            center_barcode if center_barcode is not None else src.get("center_barcode"),
            opt.center_barcode,
        ),
        center_content=_parse_bool(
            center_content if center_content is not None else src.get("center_content"),
            opt.center_content,
        ),
    )



def detect_barcode_x_bounds(sub_mask: np.ndarray) -> Optional[Tuple[int, int]]:
    """在单个标签单元的二值墨水子图中检测 Code 128 / Code 39 条码的左右边界 (像素坐标)。"""
    if sub_mask.shape[0] < 5 or sub_mask.shape[1] < 20:
        return None
    diff = np.diff(sub_mask.astype(np.int8), axis=1) != 0
    transitions = np.sum(diff, axis=1)
    bc_rows = np.where(transitions >= 16)[0]
    if bc_rows.size < 3:
        return None
    bc_sub = sub_mask[bc_rows.min() : bc_rows.max() + 1, :]
    col_ink = bc_sub.any(axis=0)
    bc_cols = np.where(col_ink)[0]
    if bc_cols.size == 0:
        return None
    return int(bc_cols.min()), int(bc_cols.max())

@dataclass(frozen=True)
class LabelBox:
    page_index: int
    rect: fitz.Rect
    vis_rect: fitz.Rect | None = None
    rotation: int = 0
    barcode_center_x: float | None = None


@dataclass(frozen=True)
class ProcessedFile:
    index: int
    name: str
    pdf_bytes: bytes
    label_count: int
    page_count: int


@dataclass(frozen=True)
class _PageDetectJob:
    file_index: int
    page_index: int
    pdf_bytes: bytes


def _detect_page_job(job: _PageDetectJob, opt: ProcessOptions) -> Tuple[int, List[LabelBox]]:
    """单页墨迹检测（独立打开 Document，可安全并行）。"""
    doc = fitz.open(stream=job.pdf_bytes, filetype="pdf")
    try:
        proc = PDFLabelProcessor(opt)
        return job.file_index, proc._detect_page_labels(doc[job.page_index], job.page_index)
    finally:
        doc.close()


def _compose_file_job(
    file_index: int,
    name: str,
    pdf_bytes: bytes,
    boxes: List[LabelBox],
    size: LabelSize,
    opt: ProcessOptions,
) -> ProcessedFile:
    proc = PDFLabelProcessor(opt)
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        row_tol = mm_to_pt(opt.min_label_mm)
        ordered = sorted(
            boxes,
            key=lambda b: (
                b.page_index,
                round((b.vis_rect or b.rect).y0 / row_tol),
                (b.vis_rect or b.rect).x0,
            ),
        )
        out_bytes = proc._compose(src, ordered, size)
        out_doc = fitz.open(stream=out_bytes, filetype="pdf")
        try:
            page_count = out_doc.page_count
        finally:
            out_doc.close()
        return ProcessedFile(
            index=file_index,
            name=name,
            pdf_bytes=out_bytes,
            label_count=len(ordered),
            page_count=page_count,
        )
    finally:
        src.close()


class PDFLabelProcessor:
    """智能裁剪 + 重排核心类。"""

    def __init__(self, options: ProcessOptions | None = None) -> None:
        self.opt = options or ProcessOptions()

    def process(self, pdf_bytes: bytes, size: LabelSize) -> bytes:
        src = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            boxes = self._detect_all_labels(src, pdf_bytes)
            return self._compose(src, boxes, size)
        finally:
            src.close()

    def process_named(
        self,
        name: str,
        pdf_bytes: bytes,
        size: LabelSize,
        index: int = 0,
    ) -> ProcessedFile:
        src = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            boxes = self._detect_all_labels(src, pdf_bytes)
            out_bytes = self._compose(src, boxes, size)
            out_doc = fitz.open(stream=out_bytes, filetype="pdf")
            try:
                page_count = out_doc.page_count
            finally:
                out_doc.close()
            return ProcessedFile(
                index=index,
                name=name,
                pdf_bytes=out_bytes,
                label_count=len(boxes),
                page_count=page_count,
            )
        finally:
            src.close()

    def process_many(self, pdf_bytes_list: Sequence[bytes], size: LabelSize) -> bytes:
        items = [(f"file_{i + 1}.pdf", data) for i, data in enumerate(pdf_bytes_list) if data]
        return merge_pdf_bytes(
            [r.pdf_bytes for r in process_files_parallel(items, size, options=self.opt)]
        )

    def _detect_all_labels(self, doc: fitz.Document, pdf_bytes: bytes | None = None) -> List[LabelBox]:
        page_count = doc.page_count
        if page_count == 0:
            return []
        if page_count == 1:
            return self._detect_page_labels(doc[0], 0)

        raw = pdf_bytes if pdf_bytes is not None else doc.tobytes()
        workers = resolve_worker_count(self.opt, page_count)
        jobs = [_PageDetectJob(0, pno, raw) for pno in range(page_count)]
        boxes: List[LabelBox] = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for _, page_boxes in executor.map(
                lambda job: _detect_page_job(job, self.opt),
                jobs,
            ):
                boxes.extend(page_boxes)

        row_tol = mm_to_pt(self.opt.min_label_mm)
        boxes.sort(
            key=lambda b: (
                b.page_index,
                round((b.vis_rect or b.rect).y0 / row_tol),
                (b.vis_rect or b.rect).x0,
            )
        )
        return boxes

    def _detect_page_labels(self, page: fitz.Page, pno: int) -> List[LabelBox]:
        opt = self.opt
        scale = opt.detect_dpi / PT_PER_INCH
        # S9 DoS ?????????? (1700 pt) ??????? 4096px??? 2.2GB ????
        max_page_pt = max(page.rect.width, page.rect.height)
        if max_page_pt > MAX_PHYSICAL_PAGE_PT or (max_page_pt * scale) > MAX_RASTER_DIM_PX:
            scale = min(scale, MAX_RASTER_DIM_PX / max(max_page_pt, 1.0))

        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
        try:
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
            ink = img < opt.ink_threshold
            self._mask_ignore_regions(ink, scale, opt.ignore_top_mm, opt.ignore_bottom_mm)
        finally:
            del pix

        if not ink.any():
            del img, ink
            return []

        gap_px = max(1, int(round(mm_to_pt(opt.merge_gap_mm) * scale)))
        closed = self._dilate(ink, gap_px)
        clusters = self._connected_components(closed)

        min_px = mm_to_pt(opt.min_label_mm) * scale
        pad_pt = mm_to_pt(opt.padding_mm)
        page_rect = page.rect
        derot = page.derotation_matrix
        page_rot = page.rotation

        result: List[LabelBox] = []
        for x0, y0, x1, y1 in clusters:
            sub = ink[y0 : y1 + 1, x0 : x1 + 1]
            ys, xs = np.where(sub)
            if xs.size == 0:
                continue
            rx0 = (x0 + int(xs.min())) / scale
            ry0 = (y0 + int(ys.min())) / scale
            rx1 = (x0 + int(xs.max()) + 1) / scale
            ry1 = (y0 + int(ys.max()) + 1) / scale

            if (rx1 - rx0) * scale < min_px or (ry1 - ry0) * scale < min_px:
                continue

            vis_rx0, vis_rx1 = rx0, rx1
            bc_center_pt: float | None = None
            if opt.center_barcode:
                bc_bounds = detect_barcode_x_bounds(sub)
                if bc_bounds is not None:
                    bc_x0_pt = (x0 + bc_bounds[0]) / scale
                    bc_x1_pt = (x0 + bc_bounds[1] + 1) / scale
                    bc_center_pt = (bc_x0_pt + bc_x1_pt) / 2.0
                    max_half = max(bc_center_pt - rx0, rx1 - bc_center_pt)
                    vis_rx0 = bc_center_pt - max_half
                    vis_rx1 = bc_center_pt + max_half

            vis_rect = fitz.Rect(vis_rx0 - pad_pt, ry0 - pad_pt, vis_rx1 + pad_pt, ry1 + pad_pt)
            if vis_rect.is_empty:
                continue
            clip_rect = (vis_rect * derot).normalize()
            result.append(
                LabelBox(
                    pno,
                    clip_rect,
                    vis_rect=vis_rect,
                    rotation=page_rot,
                    barcode_center_x=bc_center_pt,
                )
            )

        row_tol = mm_to_pt(opt.min_label_mm)
        result.sort(key=lambda b: (round((b.vis_rect or b.rect).y0 / row_tol), (b.vis_rect or b.rect).x0))
        del img, ink, closed, clusters
        return result

    @staticmethod
    def _mask_ignore_regions(
        ink: np.ndarray,
        scale: float,
        ignore_top_mm: float,
        ignore_bottom_mm: float,
    ) -> None:
        h = ink.shape[0]
        if ignore_top_mm > 0:
            top_px = min(h, int(round(mm_to_pt(ignore_top_mm) * scale)))
            if top_px > 0:
                ink[:top_px, :] = False
        if ignore_bottom_mm > 0:
            bottom_px = min(h, int(round(mm_to_pt(ignore_bottom_mm) * scale)))
            if bottom_px > 0:
                ink[h - bottom_px :, :] = False

    def _compose(self, src: fitz.Document, boxes: List[LabelBox], size: LabelSize) -> bytes:
        out = fitz.open()
        try:
            self._render_into(out, src, boxes, size)
            if out.page_count == 0:
                out.new_page(width=size.width_pt, height=size.height_pt)
            return out.tobytes(deflate=True, garbage=4)
        finally:
            out.close()

    def _is_carrier_4x6(self, src: fitz.Document, box: LabelBox) -> bool:
        bw, bh = box.rect.width, box.rect.height
        if bw <= 0 or bh <= 0:
            return False
        aspect = max(bw, bh) / min(bw, bh)
        if not (1.32 <= aspect <= 1.68):
            return False
        try:
            text = src[box.page_index].get_text("text", clip=box.rect).upper()
            carrier_keywords = ("UPS", "1Z ", "FEDEX", "TRACKING", "CARRIER", "MAXICODE", "BILLING: P/P")
            return any(k in text for k in carrier_keywords)
        except Exception:
            return False

    def _render_into(
        self,
        out: fitz.Document,
        src: fitz.Document,
        boxes: List[LabelBox],
        size: LabelSize,
    ) -> None:
        tw, th = size.width_pt, size.height_pt
        margin = self.opt.margin_ratio
        bottom_band = mm_to_pt(BOTTOM_TEXT_BAND_MM) if self.opt.custom_text else 0.0
        avail_w = tw * (1 - 2 * margin)
        avail_h = th * (1 - 2 * margin) - bottom_band

        for box in boxes:
            clip = box.rect
            vis = box.vis_rect or box.rect
            bw, bh = vis.width, vis.height
            if bw <= 0 or bh <= 0:
                continue

            curr_tw, curr_th = tw, th
            curr_avail_w, curr_avail_h = avail_w, avail_h
            if self.opt.carrier_adaptive and self._is_carrier_4x6(src, box):
                carrier_size = resolve_size("product_100x150")
                curr_tw, curr_th = carrier_size.width_pt, carrier_size.height_pt
                curr_avail_w = curr_tw * (1 - 2 * margin)
                curr_avail_h = curr_th * (1 - 2 * margin) - bottom_band

            page = out.new_page(width=curr_tw, height=curr_th)

            # 长宽比智能检测与自动旋转 (Auto-Rotate):
            # 若源标签与目标可用区域的横竖向不一致，逆时针旋转 90 度贴入，最大化填充纸张
            is_box_landscape = bw > bh
            is_target_landscape = curr_avail_w > curr_avail_h
            auto_deg = 0
            if self.opt.auto_rotate and (is_box_landscape != is_target_landscape):
                auto_deg = 270  # PyMuPDF 顺时针 270 度即逆时针 90 度
                eff_w, eff_h = bh, bw
            else:
                eff_w, eff_h = bw, bh

            total_rotate = (box.rotation + auto_deg) % 360

            ratio = min(curr_avail_w / eff_w, curr_avail_h / eff_h)
            draw_w, draw_h = eff_w * ratio, eff_h * ratio
            if self.opt.center_content:
                x = (curr_tw - draw_w) / 2
                top_bound = curr_th * margin
                slack_h = max(0.0, curr_avail_h - draw_h)
                if self.opt.custom_text:
                    # 4:5 垂直光学浮动律：消除底部自定义文本带来的下坠沉底感
                    y = top_bound + slack_h * (4.0 / 9.0)
                else:
                    # 微调光学浮动 1.5%
                    y = top_bound + slack_h * 0.485
            else:
                x = curr_tw * margin
                y = curr_th * margin
            target = fitz.Rect(x, y, x + draw_w, y + draw_h)

            page.show_pdf_page(target, src, box.page_index, clip=clip, rotate=total_rotate, keep_proportion=True)
            self._apply_bottom_custom_text(
                page,
                size if not (self.opt.carrier_adaptive and self._is_carrier_4x6(src, box)) else LabelSize("auto", "", curr_tw / PT_PER_INCH * MM_PER_INCH, curr_th / PT_PER_INCH * MM_PER_INCH)
            )

    def _apply_bottom_custom_text(self, page: fitz.Page, size: LabelSize) -> None:
        text = self.opt.custom_text
        if not text:
            return
        font_size = _bottom_text_font_size(size.height_mm)
        fontname = "china-s"
        margin = self.opt.margin_ratio
        avail_w = page.rect.width * (1 - 2 * margin)
        curr_len = fitz.get_text_length(text, fontname=fontname, fontsize=font_size)
        min_size = 4.5
        if curr_len > avail_w and curr_len > 0:
            scale = avail_w / curr_len
            scaled_size = font_size * scale
            if scaled_size < min_size:
                scaled_size = min_size
                while len(text) > 3 and fitz.get_text_length(text + "...", fontname=fontname, fontsize=scaled_size) > avail_w:
                    text = text[:-1]
                text = text + "..."
            font_size = scaled_size
        text_width = fitz.get_text_length(text, fontname=fontname, fontsize=font_size)
        x = max(page.rect.width * margin, (page.rect.width - text_width) / 2)
        band_h = mm_to_pt(BOTTOM_TEXT_BAND_MM)
        band_center_y = page.rect.height - (page.rect.height * margin) - (band_h / 2.0)
        y = band_center_y + (0.35 * font_size)
        page.insert_text((x, y), text, fontsize=font_size, fontname=fontname)

    def _dilate(self, mask: np.ndarray, radius: int) -> np.ndarray:
        if radius <= 0:
            return mask
        ndi = _scipy_ndimage()
        if ndi is not None:
            size = radius * 2 + 1
            struct = np.ones((size, size), dtype=bool)
            return ndi.binary_dilation(mask, structure=struct)
        return self._dilate_numpy(mask, radius)

    @staticmethod
    def _dilate_numpy(mask: np.ndarray, radius: int) -> np.ndarray:
        out = mask.copy()
        for axis in (0, 1):
            acc = out.copy()
            for shift in range(1, radius + 1):
                if axis == 0:
                    acc[shift:, :] |= out[:-shift, :]
                    acc[:-shift, :] |= out[shift:, :]
                else:
                    acc[:, shift:] |= out[:, :-shift]
                    acc[:, :-shift] |= out[:, shift:]
            out = acc
        return out

    def _connected_components(self, mask: np.ndarray) -> List[Tuple[int, int, int, int]]:
        if not mask.any():
            return []
        ndi = _scipy_ndimage()
        if ndi is not None:
            labeled, count = ndi.label(mask)
            if count == 0:
                return []
            slices = ndi.find_objects(labeled)
            boxes: List[Tuple[int, int, int, int]] = []
            for slc in slices:
                if slc is None:
                    continue
                y0, y1 = slc[0].start, slc[0].stop
                x0, x1 = slc[1].start, slc[1].stop
                boxes.append((x0, y0, x1 - 1, y1 - 1))
            return boxes
        return self._connected_components_numpy(mask)

    @staticmethod
    def _connected_components_numpy(mask: np.ndarray) -> List[Tuple[int, int, int, int]]:
        h, w = mask.shape
        visited = np.zeros_like(mask, dtype=bool)
        boxes: List[Tuple[int, int, int, int]] = []
        ys_all, xs_all = np.where(mask)

        for sy, sx in zip(ys_all.tolist(), xs_all.tolist()):
            if visited[sy, sx]:
                continue
            stack = [(sy, sx)]
            visited[sy, sx] = True
            minx = maxx = sx
            miny = maxy = sy
            while stack:
                cy, cx = stack.pop()
                if cx < minx:
                    minx = cx
                if cx > maxx:
                    maxx = cx
                if cy < miny:
                    miny = cy
                if cy > maxy:
                    maxy = cy
                if cx > 0 and mask[cy, cx - 1] and not visited[cy, cx - 1]:
                    visited[cy, cx - 1] = True
                    stack.append((cy, cx - 1))
                if cx < w - 1 and mask[cy, cx + 1] and not visited[cy, cx + 1]:
                    visited[cy, cx + 1] = True
                    stack.append((cy, cx + 1))
                if cy > 0 and mask[cy - 1, cx] and not visited[cy - 1, cx]:
                    visited[cy - 1, cx] = True
                    stack.append((cy - 1, cx))
                if cy < h - 1 and mask[cy + 1, cx] and not visited[cy + 1, cx]:
                    visited[cy + 1, cx] = True
                    stack.append((cy + 1, cx))
            boxes.append((minx, miny, maxx, maxy))
        return boxes


def merge_pdf_bytes(chunks: Sequence[bytes]) -> bytes:
    merged = fitz.open()
    try:
        for chunk in chunks:
            if not chunk:
                continue
            src = fitz.open(stream=chunk, filetype="pdf")
            try:
                merged.insert_pdf(src)
            finally:
                src.close()
        if merged.page_count == 0:
            merged.new_page(width=mm_to_pt(100), height=mm_to_pt(100))
        return merged.tobytes(deflate=True, garbage=4)
    finally:
        merged.close()


def process_files_parallel(
    items: Sequence[Tuple[str, bytes]],
    size: LabelSize,
    *,
    options: ProcessOptions | None = None,
    on_progress: ProgressFn | None = None,
    cancel_event: threading.Event | None = None,
) -> List[ProcessedFile]:
    """并行处理多个 PDF：跨文件 + 跨页检测，尽量占满 CPU。"""
    opt = options or ProcessOptions()
    valid = [(i, name, data) for i, (name, data) in enumerate(items) if data]
    if not valid:
        return []

    file_meta: List[Tuple[int, str, bytes, int]] = []
    page_jobs: List[_PageDetectJob] = []
    for file_index, name, pdf_bytes in valid:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        try:
            page_count = doc.page_count
        finally:
            doc.close()
        file_meta.append((file_index, name, pdf_bytes, page_count))
        for pno in range(page_count):
            page_jobs.append(_PageDetectJob(file_index, pno, pdf_bytes))

    total_files = len(file_meta)
    total_pages = len(page_jobs)
    detect_workers = resolve_worker_count(opt, total_pages)
    compose_workers = resolve_worker_count(opt, total_files)

    if on_progress:
        on_progress(
            5,
            f"启动 {detect_workers} 线程并行检测 {total_pages} 页（{total_files} 个 PDF）…",
        )

    boxes_by_file: Dict[int, List[LabelBox]] = {idx: [] for idx, _, _, _ in file_meta}
    done_pages = 0

    with ThreadPoolExecutor(max_workers=detect_workers) as executor:
        futures = {
            executor.submit(_detect_page_job, job, opt): job for job in page_jobs
        }
        for fut in as_completed(futures):
            if cancel_event and cancel_event.is_set():
                for f in futures:
                    f.cancel()
                return []
            file_index, page_boxes = fut.result()
            boxes_by_file[file_index].extend(page_boxes)
            done_pages += 1
            if on_progress and (done_pages == 1 or done_pages == total_pages or done_pages % 2 == 0):
                pct = 5 + int(70 * done_pages / max(total_pages, 1))
                on_progress(
                    pct,
                    f"并行检测 {done_pages}/{total_pages} 页（{detect_workers} 线程）…",
                )

    if on_progress:
        on_progress(78, f"检测完成，{compose_workers} 线程并行合成 {total_files} 个 PDF…")

    results: List[Optional[ProcessedFile]] = [None] * total_files
    done_files = 0

    with ThreadPoolExecutor(max_workers=compose_workers) as executor:
        futures = {
            executor.submit(
                _compose_file_job,
                file_index,
                name,
                pdf_bytes,
                boxes_by_file[file_index],
                size,
                opt,
            ): file_index
            for file_index, name, pdf_bytes, _ in file_meta
        }
        for fut in as_completed(futures):
            if cancel_event and cancel_event.is_set():
                for f in futures:
                    f.cancel()
                return []
            result = fut.result()
            results[result.index] = result
            done_files += 1
            if on_progress:
                pct = 78 + int(14 * done_files / max(total_files, 1))
                on_progress(
                    pct,
                    f"已完成 {done_files}/{total_files}：{result.name}（{result.label_count} 标签 → {result.page_count} 页）",
                )

    ordered = sorted((r for r in results if r is not None), key=lambda r: r.index)
    if on_progress:
        on_progress(92, f"全部 {len(ordered)} 个文件处理完成")
    return ordered


_DEFAULT = PDFLabelProcessor()


def resolve_size(size_key: str) -> LabelSize:
    return PRESET_SIZES.get(size_key, PRESET_SIZES["carton_100x100"])


def resolve_size_params(
    size_key: str | None = None,
    width_mm: float | None = None,
    height_mm: float | None = None,
) -> LabelSize:
    w = float(width_mm or 0)
    h = float(height_mm or 0)
    if w > 0 and h > 0:
        w = round(w, 1)
        h = round(h, 1)
        return LabelSize("custom", f"自定义 {w}×{h}mm", w, h)
    return resolve_size(str(size_key or "carton_100x100"))


def list_preset_sizes() -> List[Dict[str, str | float]]:
    return [
        {
            "key": s.key,
            "name": s.name,
            "width_mm": s.width_mm,
            "height_mm": s.height_mm,
        }
        for s in PRESET_SIZES.values()
    ]


def create_separator_banner_page(
    size: LabelSize,
    shipment_id: str = "",
    warehouse: str = "",
    box_count: int = 0,
    ticket_label: str = "",
) -> bytes:
    """生成黑带大字隔页纸，用于多货件合并批处理时物理防错隔断。"""
    w, h = size.width_pt, size.height_pt
    doc = fitz.open()
    try:
        page = doc.new_page(width=w, height=h)

        # 1. 顶部醒目反白黑带
        header_h = h * 0.20
        page.draw_rect(fitz.Rect(0, 0, w, header_h), color=(0, 0, 0), fill=(0, 0, 0))
        try:
            page.insert_text((15, header_h * 0.65), "【 换 货 件 / NEW SHIPMENT 】", fontname="china-s", fontsize=15, color=(1, 1, 1))
        except Exception:
            page.insert_text((15, header_h * 0.65), "== NEW SHIPMENT SEPARATOR ==", fontname="helv", fontsize=13, color=(1, 1, 1))

        # 2. 外层实线边框
        page.draw_rect(fitz.Rect(6, 6, w - 6, h - 6), color=(0, 0, 0), width=1.5)

        # 3. 核心货件元数据
        meta_lines = []
        if ticket_label:
            meta_lines.append((ticket_label, 13))
        sid_text = f"货件: {shipment_id}" if shipment_id else "货件: (未指定)"
        wh_text = f"目的仓: {warehouse}" if warehouse else "目的仓: (未指定)"
        cnt_text = f"共 {box_count} 箱" if box_count > 0 else "当前货件结束"
        meta_lines.append((sid_text, 14))
        meta_lines.append((wh_text, 18))
        meta_lines.append((cnt_text, 15))

        start_y = header_h + h * 0.12
        step_y = h * 0.12
        for i, (txt, sz) in enumerate(meta_lines):
            y = start_y + i * step_y
            try:
                page.insert_text((18, y), txt, fontname="china-s", fontsize=sz, color=(0, 0, 0))
            except Exception:
                page.insert_text((18, y), txt, fontname="helv", fontsize=sz, color=(0, 0, 0))

        # 4. 中间流水线作业安全提醒框
        warn_y0 = h * 0.68
        warn_y1 = h * 0.83
        page.draw_rect(fitz.Rect(12, warn_y0, w - 12, warn_y1), color=(0, 0, 0), width=1)
        try:
            page.insert_text((16, warn_y0 + (warn_y1 - warn_y0) * 0.45), "⚠ 请在此撕下！下一张为新货件，切勿串箱", fontname="china-s", fontsize=9.5, color=(0, 0, 0))
            page.insert_text((16, warn_y0 + (warn_y1 - warn_y0) * 0.80), "TEAR OFF HERE - NEXT LABEL IS NEW SHIPMENT", fontname="helv", fontsize=7.5, color=(0, 0, 0))
        except Exception:
            page.insert_text((16, warn_y0 + (warn_y1 - warn_y0) * 0.50), "TEAR OFF HERE - NEW SHIPMENT", fontname="helv", fontsize=9.0, color=(0, 0, 0))

        # 5. 底部防错黑条
        footer_y0 = h * 0.88
        page.draw_rect(fitz.Rect(0, footer_y0, w, h), color=(0, 0, 0), fill=(0, 0, 0))
        try:
            page.insert_text((20, footer_y0 + (h - footer_y0) * 0.65), "■■■ 货件分割标识 / SHIPMENT BREAK ■■■", fontname="china-s", fontsize=9.5, color=(1, 1, 1))
        except Exception:
            page.insert_text((20, footer_y0 + (h - footer_y0) * 0.65), "■■■ SHIPMENT BREAK ■■■", fontname="helv", fontsize=9.5, color=(1, 1, 1))

        return doc.tobytes(deflate=True, garbage=4)
    finally:
        doc.close()


def thermal_labels_pdf(
    pdf_bytes_list: Sequence[bytes],
    size_key: str = "carton_100x100",
    *,
    width_mm: float | None = None,
    height_mm: float | None = None,
    on_progress: ProgressFn | None = None,
    names: Sequence[str] | None = None,
    options: ProcessOptions | None = None,
    shipments_meta: Sequence[Dict[str, Any]] | None = None,
) -> bytes:
    size = resolve_size_params(size_key, width_mm, height_mm)
    opt = options or ProcessOptions()
    items: List[Tuple[str, bytes]] = []
    for i, data in enumerate(pdf_bytes_list):
        if not data:
            continue
        label = names[i] if names and i < len(names) else f"file_{i + 1}.pdf"
        items.append((label, data))
    if not items:
        return merge_pdf_bytes([])
    processed = process_files_parallel(items, size, options=opt, on_progress=on_progress)
    if not processed:
        return merge_pdf_bytes([])

    chunks: List[bytes] = []
    total_items = len(processed)
    for i, p in enumerate(processed):
        chunks.append(p.pdf_bytes)
        if opt.insert_separator and total_items > 1:
            meta = (shipments_meta[i] if shipments_meta and i < len(shipments_meta) else {}) or {}
            sid = str(meta.get("shipment_id") or "")
            wh = str(meta.get("warehouse") or "")
            box_cnt = int(meta.get("carton_count") or meta.get("box_count") or p.page_count or 0)
            ticket = str(meta.get("ticket_label") or "")

            if not sid:
                parsed = parse_box_label_pdf_name(p.name)
                sid = parsed.shipment_id
                wh = wh or parsed.warehouse
                ticket = ticket or parsed.ticket_prefix

            banner_bytes = create_separator_banner_page(
                size=size,
                shipment_id=sid or f"FBA-SHIP-{i + 1}",
                warehouse=wh,
                box_count=box_cnt or p.page_count,
                ticket_label=ticket,
            )
            chunks.append(banner_bytes)

    return merge_pdf_bytes(chunks)
