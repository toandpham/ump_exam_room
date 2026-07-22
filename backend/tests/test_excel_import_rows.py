"""AD-90: file Excel khai báo vùng dữ liệu SAI không được làm mất thí sinh.

Sự cố thực địa 22-07: danh sách 420 thí sinh, hệ thống chỉ nhận 400 — không báo
lỗi dòng nào. Nguyên nhân: openpyxl ở chế độ read_only tin vào thẻ
``<dimension ref=.../>`` trong file; nhiều công cụ ghi thẻ này sai nên vòng lặp
dừng sớm. ``parse_rows`` nay gọi ``reset_dimensions()``.
"""

import io
import re
import zipfile

from openpyxl import Workbook

from app.services import excel_service


def _rows(n: int) -> list[list]:
    return [
        [f"0792000000{i:02d}", f"Thí sinh {i}", "1995-05-20", "Đơn vị A",
         2017, "Y đa khoa", "Đối tượng 1", 1, "Phòng 1"]
        for i in range(1, n + 1)
    ]


def _workbook_bytes(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(excel_service.HEADERS)
    for r in rows:
        ws.append(r)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _break_dimension(xlsx: bytes, fake_last_row: int) -> bytes:
    """Ghi đè thẻ <dimension> thành vùng NGẮN HƠN dữ liệu thật (mô phỏng file do
    công cụ khác xuất ra)."""
    src = zipfile.ZipFile(io.BytesIO(xlsx))
    out_buf = io.BytesIO()
    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.startswith("xl/worksheets/sheet"):
                text = data.decode("utf-8")
                text, n = re.subn(r'<dimension ref="[^"]+"/>',
                                  f'<dimension ref="A1:I{fake_last_row}"/>', text)
                assert n == 1, "không tìm thấy thẻ dimension để phá"
                data = text.encode("utf-8")
            out.writestr(item, data)
    return out_buf.getvalue()


def test_parse_rows_reads_every_row_of_a_healthy_file():
    parsed = excel_service.parse_rows(_workbook_bytes(_rows(25)))
    assert len(parsed) == 25
    assert parsed[0][0] == 2 and parsed[-1][0] == 26      # số dòng Excel 1-based


def test_parse_rows_ignores_a_wrong_dimension_declaration():
    xlsx = _break_dimension(_workbook_bytes(_rows(25)), fake_last_row=6)
    parsed = excel_service.parse_rows(xlsx)
    assert len(parsed) == 25, "dòng cuối bị nuốt vì tin vào thẻ dimension sai"
    # Dòng cuối vẫn đọc được đầy đủ (không phải ô rỗng).
    data, errors = excel_service.validate_row(parsed[-1][1])
    assert errors == []
    assert data["full_name"] == "Thí sinh 25"
