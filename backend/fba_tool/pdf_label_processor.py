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
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import fitz  # PyMuPDF
import numpy as np

try:
    from scipy import ndimage as scipy_ndimage

    _HAS_SCIPY = True
except ImportError:  # pragma: no cover
    scipy_ndimage = None  # type: ignore
    _HAS_SCIPY = False

MM_PER_INCH = 25.4
PT_PER_INCH = 72.0
ALLOWED_DETECT_DPIS = (120, 200, 300)
BOTTOM_TEXT_BAND_MM = 4.0
MAX_CUSTOM_TEXT_LEN = 80

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
    padding_mm: float = 1.0
    margin_ratio: float = 0.008
    max_workers: int = 0  # 0 = auto
    ignore_top_mm: float = 0.0
    ignore_bottom_mm: float = 0.0
    custom_text: Optional[str] = None


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


def parse_process_options(
    source: Mapping[str, Any] | None = None,
    *,
    base: ProcessOptions | None = None,
    padding_mm: Any = None,
    ignore_top_mm: Any = None,
    ignore_bottom_mm: Any = None,
    detect_dpi: Any = None,
    custom_text: Any = None,
) -> ProcessOptions:
    """从 dict / Form 字段统一解析 ProcessOptions（Phase 1 开放参数）。"""
    opt = base or ProcessOptions()
    src = source or {}
    return replace(
        opt,
        padding_mm=_clamp_nonneg_float(
            padding_mm if padding_mm is not None else src.get("padding_mm"),
            opt.padding_mm,
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
    )


@dataclass(frozen=True)
class LabelBox:
    page_index: int
    rect: fitz.Rect


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
            key=lambda b: (b.page_index, round(b.rect.y0 / row_tol), b.rect.x0),
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
        boxes.sort(key=lambda b: (b.page_index, round(b.rect.y0 / row_tol), b.rect.x0))
        return boxes

    def _detect_page_labels(self, page: fitz.Page, pno: int) -> List[LabelBox]:
        opt = self.opt
        scale = opt.detect_dpi / PT_PER_INCH
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

            rect = fitz.Rect(rx0 - pad_pt, ry0 - pad_pt, rx1 + pad_pt, ry1 + pad_pt)
            rect &= page_rect
            if rect.is_empty:
                continue
            result.append(LabelBox(pno, rect))

        row_tol = mm_to_pt(opt.min_label_mm)
        result.sort(key=lambda b: (round(b.rect.y0 / row_tol), b.rect.x0))
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
            page = out.new_page(width=tw, height=th)
            clip = box.rect
            bw, bh = clip.width, clip.height
            if bw <= 0 or bh <= 0:
                continue
            ratio = min(avail_w / bw, avail_h / bh)
            draw_w, draw_h = bw * ratio, bh * ratio
            x = (tw - draw_w) / 2
            y = (th - draw_h) / 2
            target = fitz.Rect(x, y, x + draw_w, y + draw_h)
            page.show_pdf_page(target, src, box.page_index, clip=clip)
            self._apply_bottom_custom_text(page, size)

    def _apply_bottom_custom_text(self, page: fitz.Page, size: LabelSize) -> None:
        text = self.opt.custom_text
        if not text:
            return
        font_size = _bottom_text_font_size(size.height_mm)
        text_width = fitz.get_text_length(text, fontname="helv", fontsize=font_size)
        x = max(0.0, (page.rect.width - text_width) / 2)
        y = page.rect.height - mm_to_pt(2.5)
        page.insert_text((x, y), text, fontsize=font_size, fontname="helv")

    def _dilate(self, mask: np.ndarray, radius: int) -> np.ndarray:
        if radius <= 0:
            return mask
        if _HAS_SCIPY:
            size = radius * 2 + 1
            struct = np.ones((size, size), dtype=bool)
            return scipy_ndimage.binary_dilation(mask, structure=struct)
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
        if _HAS_SCIPY:
            labeled, count = scipy_ndimage.label(mask)
            if count == 0:
                return []
            slices = scipy_ndimage.find_objects(labeled)
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


def thermal_labels_pdf(
    pdf_bytes_list: Sequence[bytes],
    size_key: str = "carton_100x100",
    *,
    width_mm: float | None = None,
    height_mm: float | None = None,
    on_progress: ProgressFn | None = None,
    names: Sequence[str] | None = None,
    options: ProcessOptions | None = None,
) -> bytes:
    size = resolve_size_params(size_key, width_mm, height_mm)
    items: List[Tuple[str, bytes]] = []
    for i, data in enumerate(pdf_bytes_list):
        if not data:
            continue
        label = names[i] if names and i < len(names) else f"file_{i + 1}.pdf"
        items.append((label, data))
    if not items:
        return merge_pdf_bytes([])
    processed = process_files_parallel(items, size, options=options, on_progress=on_progress)
    return merge_pdf_bytes([p.pdf_bytes for p in processed])
