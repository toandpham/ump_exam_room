"""Đọc phiếu trả lời đã quét.

Chuỗi xử lý:

1. Ảnh xám → nhị phân (ngưỡng Otsu, tự thích nghi với bản quét đậm/nhạt).
2. Tìm bốn dấu định vị: trong mỗi góc, tìm ô vuông ĐẶC nhất (dấu định vị là khối
   đen liền 6×6mm, đậm hơn hẳn nét chữ). Cố ý không lấy trọng tâm cả vùng góc —
   chữ in gần đó sẽ kéo tâm lệch vài milimét, đủ để đọc sai cả tờ.
3. Từ bốn cặp điểm (mm ↔ pixel) dựng phép biến đổi phối cảnh — bù cả xoay, lệch
   tỉ lệ lẫn méo hình do đặt nghiêng trên mặt kính máy quét.
4. Mỗi bóng: chiếu tâm sang toạ độ ảnh, lấy độ đậm trung bình trong đĩa nhỏ.
5. Quyết định: chọn bóng đậm nhất, nhưng CHỈ khi nó đủ đậm VÀ cách biệt rõ với
   bóng nhì. Không đạt thì trả về "cần xem lại" thay vì đoán bừa — chấm sai một
   bài vì máy đoán ẩu còn tệ hơn bắt người ta nhập tay vài tờ.

Cố ý KHÔNG dùng thư viện thị giác máy tính nặng: chỉ numpy + Pillow, vốn đã có
sẵn (Pillow) hoặc rất nhẹ (numpy). Bài toán này đơn giản vì ta kiểm soát cả tờ in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from . import geometry as g

# Ngưỡng quyết định trên thang 0 (trắng) .. 1 (đen đặc).
MIN_DARKNESS = 0.35        # tô mờ hơn mức này thì coi như không tô
MIN_MARGIN = 0.18          # bóng nhất phải đậm hơn bóng nhì chừng này
CODE_DARKNESS = 0.5        # bóng mã do máy in tô đặc → ngưỡng chặt hơn


class OmrError(Exception):
    """Không đọc nổi tờ này (thiếu dấu định vị, ảnh hỏng…)."""


@dataclass
class SheetResult:
    candidate_index: int
    page: int
    # {chỉ số câu (0-based theo đề): "A"/"B"/"C"/"D"}
    answers: dict[int, str] = field(default_factory=dict)
    # Các câu máy không dám quyết (bỏ trống, tô hai ô, tô quá mờ).
    unsure: list[int] = field(default_factory=list)


def _to_gray(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=np.float32) / 255.0


def _otsu(gray: np.ndarray) -> float:
    """Ngưỡng Otsu — tách nền/mực mà không phải đoán trước bản quét đậm hay nhạt."""
    hist, edges = np.histogram(gray, bins=256, range=(0.0, 1.0))
    total = gray.size
    w = np.cumsum(hist)
    centers = (edges[:-1] + edges[1:]) / 2
    m = np.cumsum(hist * centers)
    m_total = m[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (m_total * w / total - m) ** 2 / (w * (total - w) / total)
    between = np.nan_to_num(between)
    return float(centers[int(np.argmax(between))])


def _corner_fiducial(dark: np.ndarray, quadrant: str, win_px: int,
                     box_px: int) -> tuple[float, float]:
    """Tâm dấu định vị ở một góc ảnh.

    KHÔNG lấy trọng tâm cả vùng góc: chữ in gần đó (tên kỳ thi, dòng hướng dẫn) sẽ
    kéo tâm lệch vài milimét — đủ để đọc sai cả tờ. Thay vào đó tìm ô vuông ĐẶC
    NHẤT: dấu định vị là khối đen liền 6×6mm, đậm hơn hẳn nét chữ vốn mảnh. Dùng
    ảnh tích phân nên quét toàn vùng vẫn nhanh.
    """
    h, w = dark.shape
    win_y, win_x = min(win_px, h), min(win_px, w)
    y0 = 0 if quadrant[0] == "t" else h - win_y
    x0 = 0 if quadrant[1] == "l" else w - win_x
    patch = dark[y0:y0 + win_y, x0:x0 + win_x].astype(np.float32)
    if patch.sum() < 20:
        raise OmrError(f"Không tìm thấy dấu định vị ở góc {quadrant}.")

    b = max(3, min(box_px, min(patch.shape) - 1))
    integral = np.pad(patch, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    sums = (integral[b:, b:] - integral[:-b, b:]
            - integral[b:, :-b] + integral[:-b, :-b])
    iy, ix = np.unravel_index(int(np.argmax(sums)), sums.shape)
    if sums[iy, ix] < 0.5 * b * b:
        raise OmrError(f"Không tìm thấy dấu định vị ở góc {quadrant}.")

    # Tinh chỉnh: trọng tâm điểm đen bên trong ô vừa tìm được.
    sub = patch[iy:iy + b, ix:ix + b]
    ys, xs = np.nonzero(sub)
    return float(xs.mean() + ix + x0), float(ys.mean() + iy + y0)


def _homography(src: list[tuple[float, float]],
                dst: list[tuple[float, float]]) -> np.ndarray:
    """Ma trận 3×3 đưa toạ độ mm (src) sang toạ độ ảnh (dst), từ 4 cặp điểm."""
    a = []
    b = []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    sol, *_ = np.linalg.lstsq(np.asarray(a, dtype=np.float64),
                             np.asarray(b, dtype=np.float64), rcond=None)
    return np.append(sol, 1.0).reshape(3, 3)


def _project(h: np.ndarray, x_mm: float, y_mm: float) -> tuple[float, float]:
    v = h @ np.array([x_mm, y_mm, 1.0])
    return float(v[0] / v[2]), float(v[1] / v[2])


def _darkness(dark: np.ndarray, h: np.ndarray, b: g.Bubble) -> float:
    """Tỉ lệ điểm đen trong đĩa quanh tâm bóng (0..1).

    Bán kính lấy nhỏ hơn bóng in để viền tròn của bóng không tự làm nó "đậm" —
    nếu không thì bóng trống cũng vượt ngưỡng."""
    cx, cy = _project(h, b.x_mm, b.y_mm)
    # Bán kính theo pixel: đo bằng chính phép chiếu, để đúng cả khi ảnh quét ở
    # độ phân giải bất kỳ.
    ex, ey = _project(h, b.x_mm + g.BUBBLE_R_MM * 0.6, b.y_mm)
    r = max(2.0, ((ex - cx) ** 2 + (ey - cy) ** 2) ** 0.5)
    h_img, w_img = dark.shape
    x0, x1 = max(0, int(cx - r)), min(w_img, int(cx + r) + 1)
    y0, y1 = max(0, int(cy - r)), min(h_img, int(cy + r) + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    ys, xs = np.mgrid[y0:y1, x0:x1]
    mask = (xs - cx) ** 2 + (ys - cy) ** 2 <= r * r
    if not mask.any():
        return 0.0
    return float(dark[y0:y1, x0:x1][mask].mean())


def read_sheet(img: Image.Image, total_questions: int) -> SheetResult:
    """Đọc MỘT tờ đã quét."""
    gray = _to_gray(img)
    dark = gray < _otsu(gray)

    # Cỡ pixel ước lượng từ chiều rộng ảnh (bản quét nghiêng thì hơi lệch, nhưng
    # chỉ dùng để định cỡ cửa sổ tìm kiếm nên không cần chính xác).
    px_per_mm = gray.shape[1] / g.PAGE_W_MM
    win = int(g.CORNER_SEARCH_MM * 1.6 * px_per_mm)
    box = int(g.FIDUCIAL_SIZE_MM * px_per_mm)
    found = [_corner_fiducial(dark, q, win, box) for q in ("tl", "tr", "bl", "br")]
    h = _homography(list(g.FIDUCIALS_MM), found)

    dark_f = dark.astype(np.float32)

    def marked(b: g.Bubble, threshold: float) -> bool:
        return _darkness(dark_f, h, b) >= threshold

    candidate_index = g.decode_bits([marked(b, CODE_DARKNESS) for b in g.id_bubbles()])
    page = g.decode_bits([marked(b, CODE_DARKNESS) for b in g.page_bubbles()])

    res = SheetResult(candidate_index=candidate_index, page=page)
    for i, q_index in enumerate(g.questions_on_page(total_questions, page)):
        vals = [_darkness(dark_f, h, b) for b in g.option_bubbles(i)]
        order = np.argsort(vals)[::-1]
        best, second = int(order[0]), int(order[1])
        if vals[best] >= MIN_DARKNESS and vals[best] - vals[second] >= MIN_MARGIN:
            res.answers[q_index] = g.OPTIONS[best]
        elif vals[best] >= MIN_DARKNESS:
            # Đủ đậm nhưng không tách bạch → tô hai ô, hoặc tẩy chưa sạch.
            res.unsure.append(q_index)
        # Không ô nào đủ đậm = bỏ trống, đó là câu trả lời hợp lệ (không tô).
    return res


def images_from_upload(data: bytes, filename: str) -> list[Image.Image]:
    """Ảnh quét hoặc PDF nhiều trang → danh sách ảnh.

    PDF được dựng ở 200 DPI: đủ để phân biệt bóng tô, mà không làm ảnh phình to
    khiến máy chủ tốn bộ nhớ khi xử lý hàng trăm tờ."""
    if filename.lower().endswith(".pdf"):
        import pypdfium2

        pdf = pypdfium2.PdfDocument(data)
        try:
            return [page.render(scale=200 / 72).to_pil() for page in pdf]
        finally:
            pdf.close()
    import io as _io

    return [Image.open(_io.BytesIO(data))]
