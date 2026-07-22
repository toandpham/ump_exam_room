"""Chỉ cho thi bằng PHẦN MỀM KIOSK (AD-91).

Yêu cầu vận hành: thí sinh chỉ được làm bài trong ứng dụng kiosk (Electron, có
khoá phím/toàn màn hình), KHÔNG được dùng Firefox/Chrome hay bất kỳ trình duyệt
thường nào — kể cả khi họ mở đúng địa chỉ máy chủ.

Nhận diện kiosk bằng 2 dấu hiệu (chỉ cần 1):
  1. Header ``X-Exam-Kiosk`` — bản kiosk từ 1.3.0 gửi kèm mọi request.
  2. Chuỗi ``Electron/`` trong User-Agent — mọi bản kiosk ĐÃ PHÁT (1.2.0 trở về
     trước) đều có sẵn, nên bật khoá không cần cài lại 400 máy.

GIỚI HẠN phải nói thẳng: đây là RÀO CẢN, không phải chứng thực. Người biết việc
có thể sửa User-Agent của trình duyệt để giả kiosk. Nó chặn được việc thí sinh mở
Firefox/Chrome lên thi (kịch bản thật cần chặn), còn chống gian lận thực sự vẫn
dựa vào kiosk khoá máy + giám thị coi thi.
"""

from __future__ import annotations

from fastapi import Request

KIOSK_HEADER = "x-exam-kiosk"

# Dấu hiệu trong User-Agent của ứng dụng kiosk (Electron).
_UA_MARKERS = ("electron/", "ump_examkiosk", "exam-kiosk")


def is_kiosk_request(request: Request) -> bool:
    """Request này có đến từ ứng dụng kiosk không?"""
    if request.headers.get(KIOSK_HEADER):
        return True
    ua = request.headers.get("user-agent", "").lower()
    return any(marker in ua for marker in _UA_MARKERS)
