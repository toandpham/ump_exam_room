"""Hình học phiếu trả lời giấy — hợp đồng CHUNG giữa bên in và bên đọc.

Mọi toạ độ tính bằng **milimét**, gốc ở góc trên bên trái tờ A4 (210×297mm), trục y
hướng xuống. Bên in (reportlab, gốc dưới trái) tự đổi trục; bên đọc quy về đúng hệ
này qua bốn dấu định vị. Chỉ cần MỘT chỗ định nghĩa để hai bên không bao giờ lệch
nhau — lệch một milimét là đọc sai cả tờ.

Bố cục:

    ■ (dấu định vị)                                    ■
      ┌──────────────────────────────────────────────┐
      │ Tiêu đề: kỳ thi · buổi · họ tên · số báo danh│
      │ ○○○○○○○○○○○○○○  ← mã thí sinh (nhị phân)     │
      │ ○○○   ← số tờ                                 │
      │ 1  ⒶⒷⒸⒹ    26 ⒶⒷⒸⒹ    51 ⒶⒷⒸⒹ    76 ⒶⒷⒸⒹ │
      │ …                                             │
      └──────────────────────────────────────────────┘
    ■                                                  ■

Vì sao mã thí sinh in bằng **bóng tròn nhị phân** chứ không phải chữ: đọc chữ cần
nhận dạng ký tự (một tầng công nghệ nữa, sai nhiều với bản quét mờ), trong khi bóng
tròn thì dùng đúng bộ đọc đã có cho phần đáp án. Số báo danh vẫn được in bằng chữ
bên cạnh để người xử lý đối chiếu bằng mắt khi máy đọc thất bại.
"""

from __future__ import annotations

from dataclasses import dataclass

PAGE_W_MM = 210.0
PAGE_H_MM = 297.0

# Dấu định vị: vuông đen đặc ở bốn góc. Vùng góc 25×25mm phải TRỐNG hoàn toàn ngoài
# dấu này — bộ đọc tìm dấu bằng cách lấy trọng tâm điểm đen trong vùng đó, nên chữ
# nghĩa lọt vào là lệch tâm.
FIDUCIAL_SIZE_MM = 6.0
FIDUCIAL_MARGIN_MM = 12.0
CORNER_SEARCH_MM = 25.0

FIDUCIALS_MM: list[tuple[float, float]] = [
    (FIDUCIAL_MARGIN_MM, FIDUCIAL_MARGIN_MM),                        # trên-trái
    (PAGE_W_MM - FIDUCIAL_MARGIN_MM, FIDUCIAL_MARGIN_MM),            # trên-phải
    (FIDUCIAL_MARGIN_MM, PAGE_H_MM - FIDUCIAL_MARGIN_MM),            # dưới-trái
    (PAGE_W_MM - FIDUCIAL_MARGIN_MM, PAGE_H_MM - FIDUCIAL_MARGIN_MM),  # dưới-phải
]

BUBBLE_R_MM = 2.2

# Mã thí sinh + số tờ, mã hoá nhị phân bằng bóng tròn (bit cao ở bên trái).
ID_BITS = 14          # 16.384 thí sinh — thừa cho mọi kỳ thi của trường
PAGE_BITS = 3         # 8 tờ mỗi thí sinh
ID_ROW_Y_MM = 47.0
PAGE_ROW_Y_MM = 55.0
CODE_X0_MM = 24.0
CODE_STEP_MM = 7.0

# Lưới đáp án: mỗi cột 25 câu, bốn cột một tờ → 100 câu mỗi tờ.
ROWS_PER_COL = 25
COLS_PER_PAGE = 4
QUESTIONS_PER_PAGE = ROWS_PER_COL * COLS_PER_PAGE

GRID_X0_MM = 20.0          # mép trái cột đầu
GRID_Y0_MM = 70.0          # tâm hàng đầu
COL_W_MM = 46.0
ROW_H_MM = 8.0
NUM_W_MM = 11.0            # chỗ in số câu, trước bóng A
OPT_STEP_MM = 8.0

OPTIONS = ("A", "B", "C", "D")


@dataclass(frozen=True)
class Bubble:
    """Một bóng tròn trên tờ: tâm (mm) + ý nghĩa."""
    x_mm: float
    y_mm: float


def page_count(total_questions: int) -> int:
    if total_questions <= 0:
        return 1
    return (total_questions + QUESTIONS_PER_PAGE - 1) // QUESTIONS_PER_PAGE


def code_bubbles(bits: int, y_mm: float) -> list[Bubble]:
    """Hàng bóng mã nhị phân, bit CAO nhất ở bên trái."""
    return [Bubble(CODE_X0_MM + i * CODE_STEP_MM, y_mm) for i in range(bits)]


def id_bubbles() -> list[Bubble]:
    return code_bubbles(ID_BITS, ID_ROW_Y_MM)


def page_bubbles() -> list[Bubble]:
    return code_bubbles(PAGE_BITS, PAGE_ROW_Y_MM)


def encode_bits(value: int, bits: int) -> list[bool]:
    """Số → danh sách bit (bit cao trước). Vượt tầm thì cắt vòng, nhưng gọi đúng
    thì không bao giờ chạm tới: 14 bit đủ 16.384 thí sinh."""
    return [bool((value >> (bits - 1 - i)) & 1) for i in range(bits)]


def decode_bits(marks: list[bool]) -> int:
    v = 0
    for m in marks:
        v = (v << 1) | (1 if m else 0)
    return v


def question_slot(index_on_page: int) -> tuple[float, float]:
    """(x mép trái ô câu, y tâm hàng) cho câu thứ ``index_on_page`` (0-based)."""
    col, row = divmod(index_on_page, ROWS_PER_COL)
    return GRID_X0_MM + col * COL_W_MM, GRID_Y0_MM + row * ROW_H_MM


def option_bubbles(index_on_page: int) -> list[Bubble]:
    """Bốn bóng A/B/C/D của một câu."""
    x0, y = question_slot(index_on_page)
    return [Bubble(x0 + NUM_W_MM + i * OPT_STEP_MM, y) for i in range(len(OPTIONS))]


def questions_on_page(total_questions: int, page: int) -> list[int]:
    """Chỉ số câu (0-based, theo thứ tự đề) nằm trên tờ ``page`` (0-based)."""
    start = page * QUESTIONS_PER_PAGE
    return list(range(start, min(start + QUESTIONS_PER_PAGE, total_questions)))
