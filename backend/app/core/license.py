"""Giấy phép sử dụng server (AD-74) — key ký Ed25519, hết hạn theo ngày.

Mô hình: server offline nên không xác thực online được. Chủ sở hữu giữ khoá bí
mật (tools/license-keygen, nằm NGOÀI repo); server chỉ nhúng khoá công khai để
kiểm chữ ký → khách không tự chế key hay sửa ngày hết hạn được.

Định dạng key: ``EXAM-<b64url(payload JSON)>.<b64url(sig)>`` — payload là JSON
canonical (sort_keys, không whitespace): ``{"exp","iat","id","to"}`` (unix giây).
Chữ ký ký trên đúng chuỗi payload đã decode, nên verify không cần re-serialize.

Chống vặn lùi đồng hồ: bảng system_license giữ ``max_seen_at`` = mốc thời gian
lớn nhất server từng thấy; nếu đồng hồ hiện tại lùi quá CLOCK_TOLERANCE so với
mốc đó → coi như can thiệp, khoá như hết hạn.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Khoá công khai của bộ keygen chính chủ (tools/license-keygen). Đổi cặp khoá
# thì thay hex này — key cũ lập tức vô hiệu.
PUBLIC_KEY_HEX = "379b525a08254874b0618e4e5f9907b4f235651fc17c24f2fb7398e1bb5df2e0"

PREFIX = "EXAM-"
# Đồng hồ được phép lệch/lùi tối đa bấy nhiêu so với mốc lớn nhất từng thấy
# (chỉnh NTP/DST hợp lệ không bị oan).
CLOCK_TOLERANCE = timedelta(hours=24)
# Cảnh báo trên dashboard khi còn ít hơn bấy nhiêu ngày.
WARN_DAYS = 14
# AD-81: cài xong tự dùng thử bấy nhiêu ngày kể từ installed_at (không cần key).
# Key gia hạn chỉ để đẩy hạn ra xa hơn mốc dùng thử này.
TRIAL_DAYS = 90


class LicenseError(ValueError):
    """Key sai định dạng / sai chữ ký — thông điệp an toàn để trả về client."""


@dataclass(frozen=True)
class LicensePayload:
    id: str
    issued_to: str
    issued_at: datetime
    expires_at: datetime


def _b64url_decode(part: str) -> bytes:
    pad = "=" * (-len(part) % 4)
    try:
        return base64.urlsafe_b64decode(part + pad)
    except (binascii.Error, ValueError) as exc:
        raise LicenseError("Key sai định dạng") from exc


def parse_key(key: str, public_key_hex: str | None = None) -> LicensePayload:
    """Kiểm định dạng + chữ ký; trả payload. KHÔNG check hết hạn ở đây.

    ``public_key_hex`` mặc định đọc PUBLIC_KEY_HEX tại thời điểm gọi (không bind
    lúc def) — để test monkeypatch được khoá công khai.
    """
    public_key_hex = public_key_hex or PUBLIC_KEY_HEX
    key = (key or "").strip()
    if not key.startswith(PREFIX) or "." not in key:
        raise LicenseError("Key sai định dạng")
    body, _, sig_part = key[len(PREFIX):].partition(".")
    raw, sig = _b64url_decode(body), _b64url_decode(sig_part)
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex)).verify(sig, raw)
    except (InvalidSignature, ValueError) as exc:
        raise LicenseError("Key không hợp lệ (sai chữ ký)") from exc
    try:
        data = json.loads(raw)
        return LicensePayload(
            id=str(data["id"]),
            issued_to=str(data["to"]),
            issued_at=datetime.fromtimestamp(int(data["iat"]), tz=timezone.utc),
            expires_at=datetime.fromtimestamp(int(data["exp"]), tz=timezone.utc),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LicenseError("Key không hợp lệ (payload hỏng)") from exc


@dataclass(frozen=True)
class LicenseState:
    """Kết quả đánh giá giấy phép tại một thời điểm.

    ``expires_at`` là hạn HIỆU LỰC đang áp dụng — của key gia hạn nếu có key hợp lệ,
    ngược lại là hạn dùng thử (installed_at + TRIAL_DAYS). ``issued_to`` chỉ có khi
    đang chạy bằng key (dùng thử không có tên đơn vị).
    """

    status: str  # valid | trial | expired | missing | clock_tampered
    expires_at: datetime | None = None
    issued_to: str | None = None

    @property
    def ok(self) -> bool:
        # Dùng thử còn hạn cũng cho chạy (AD-81).
        return self.status in ("valid", "trial")

    @property
    def days_left(self) -> int | None:
        if not self.expires_at:
            return None
        return max(0, (self.expires_at - datetime.now(timezone.utc)).days)


def evaluate(key: str | None, installed_at: datetime | None,
             max_seen_at: datetime | None,
             now: datetime | None = None,
             public_key_hex: str | None = None) -> LicenseState:
    """Đánh giá giấy phép (thuần logic — không đụng DB, dễ test).

    Ưu tiên: key gia hạn hợp lệ & còn hạn → ``valid``. Không có → xét dùng thử theo
    ``installed_at`` (+TRIAL_DAYS) → ``trial``/``expired``. Vặn lùi đồng hồ quá dung
    sai → ``clock_tampered``. Chưa cài & không key → ``missing``.
    """
    now = now or datetime.now(timezone.utc)
    tampered = bool(max_seen_at and now < max_seen_at - CLOCK_TOLERANCE)

    payload: LicensePayload | None = None
    if key:
        try:
            payload = parse_key(key, public_key_hex)
        except LicenseError:
            # Key trong DB hỏng (đổi khoá công khai / sửa tay) — bỏ qua, coi như chưa có key.
            payload = None

    if tampered:
        return LicenseState("clock_tampered",
                            expires_at=payload.expires_at if payload else None,
                            issued_to=payload.issued_to if payload else None)

    # Key gia hạn còn hiệu lực → ghi đè hạn dùng thử.
    if payload and now < payload.expires_at:
        return LicenseState("valid", expires_at=payload.expires_at, issued_to=payload.issued_to)

    # Không có key còn hạn → xét dùng thử theo mốc cài đặt.
    if installed_at:
        trial_exp = installed_at + timedelta(days=TRIAL_DAYS)
        if now < trial_exp:
            return LicenseState("trial", expires_at=trial_exp)
        # Hết dùng thử: nếu từng có key (nay đã hết hạn) báo hạn của key cho rõ.
        return LicenseState("expired", expires_at=payload.expires_at if payload else trial_exp)

    # Chưa cài (không có mốc): key hết hạn → expired; không gì cả → missing.
    if payload:
        return LicenseState("expired", expires_at=payload.expires_at)
    return LicenseState("missing")
