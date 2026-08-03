"""Bộ nạp QTI phải giữ BẢNG của đề (AD-129).

Thực địa 03-08: câu hỏi có <table> thì cả phần mềm thi lẫn màn xem đề đổ mọi ô
thành từng dòng riêng ("A / B / C / 1 / 3 / 5 / 2 / 4 / 6") — mất hoàn toàn quan hệ
hàng-cột, thí sinh không đọc được. Nguyên nhân: table/tr/td nằm trong _BLOCK_TAGS
nên mỗi ô thành một dòng.

XML dưới đây chép đúng cấu trúc nhà cung cấp dùng: không có <th>, hàng tiêu đề đánh
dấu bằng <strong> trong <td>.
"""

import xml.etree.ElementTree as ET

from app.services.qti_loader import _extract_blocks, _extract_text_and_images

TABLE = (
    '<div class="stem">'
    '<p>X-quang ngực: Phổi ứ khí.</p>'
    '<table style="border-collapse:collapse"><tbody>'
    '<tr><td><strong>A</strong></td><td><strong>B</strong></td><td><strong>C</strong></td></tr>'
    '<tr><td>1</td><td>3</td><td>5</td></tr>'
    '<tr><td>2</td><td>4</td><td>6</td></tr>'
    '</tbody></table>'
    '<p>Thái độ xử trí ban đầu nào là phù hợp nhất?</p>'
    '</div>'
)


def _blocks(xml: str):
    return _extract_blocks(ET.fromstring(xml), "/tmp")


def test_table_becomes_a_table_block_with_rows_and_columns():
    blocks = _blocks(TABLE)
    tables = [b for b in blocks if b["type"] == "table"]
    assert len(tables) == 1, blocks
    assert tables[0]["rows"] == [["A", "B", "C"], ["1", "3", "5"], ["2", "4", "6"]]


def test_table_keeps_its_position_between_the_surrounding_text():
    kinds = [b["type"] for b in _blocks(TABLE)]
    assert kinds == ["text", "table", "text"], kinds
    blocks = _blocks(TABLE)
    assert blocks[0]["text"] == "X-quang ngực: Phổi ứ khí."
    assert blocks[2]["text"] == "Thái độ xử trí ban đầu nào là phù hợp nhất?"


def test_bold_first_row_is_marked_as_header():
    """Nhà cung cấp không dùng <th>; hàng đầu in đậm chính là tiêu đề."""
    assert _blocks(TABLE)[1]["header"] is True


def test_th_row_is_also_a_header():
    b = _blocks("<div><table><tr><th>Chỉ số</th><th>Giá trị</th></tr>"
                "<tr><td>pH</td><td>7.28</td></tr></table></div>")
    assert b[0]["type"] == "table"
    assert b[0]["header"] is True
    assert b[0]["rows"] == [["Chỉ số", "Giá trị"], ["pH", "7.28"]]


def test_plain_first_row_is_not_a_header():
    b = _blocks("<div><table><tr><td>1</td><td>2</td></tr><tr><td>3</td><td>4</td></tr></table></div>")
    assert b[0]["header"] is False


def test_legacy_text_field_keeps_the_table_readable():
    """``text`` (đường cũ, đề chưa có blocks) không được NUỐT bảng — nếu bỏ qua thì
    nội dung biến mất hẳn ở mọi chỗ còn dùng text."""
    text, _ = _extract_text_and_images(ET.fromstring(TABLE), "/tmp")
    assert "A | B | C" in text
    assert "1 | 3 | 5" in text
    assert "X-quang ngực: Phổi ứ khí." in text


def test_cell_keeps_superscripts():
    """Bảng xét nghiệm hay có số mũ — phải đi qua cùng đường xử lý (AD-127)."""
    b = _blocks("<div><table><tr><td>Bạch cầu 10<sup>9</sup>/L</td></tr></table></div>")
    assert b[0]["rows"] == [["Bạch cầu 10⁹/L"]]


def test_image_inside_a_cell_is_not_lost():
    """Ảnh trong ô hiếm gặp; nếu có thì phải còn lại (đưa ra sau bảng), tuyệt đối
    không im lặng bỏ mất."""
    import app.services.qti_loader as ql
    orig = ql._load_image
    ql._load_image = lambda p: {"b64": "ZmFrZQ==", "mime": "image/jpeg"}
    try:
        b = _blocks('<div><table><tr><td>Hình<img src="x.jpg"/></td></tr></table></div>')
    finally:
        ql._load_image = orig
    assert [x["type"] for x in b] == ["table", "image"], b
    assert b[0]["rows"] == [["Hình"]]
