"""CLI nhập license key — lưới an toàn khi không vào được web (AD-74).

    docker compose exec backend python -m app.set_license '<EXAM-...>'
"""

from __future__ import annotations

import asyncio
import sys

from app.core.license import LicenseError
from app.database import AsyncSessionLocal
from app.services import license_service


async def _main(key: str) -> None:
    async with AsyncSessionLocal() as db:
        try:
            payload = await license_service.set_key(db, key)
        except LicenseError as exc:
            sys.exit(f"[LỖI] {exc}")
    print(
        f"Đã gia hạn giấy phép cho: {payload.issued_to}\n"
        f"Hết hạn: {payload.expires_at:%d/%m/%Y %H:%M} UTC\n"
        "(worker đang chạy tự nhận trong ≤60 giây — không cần restart)"
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Cách dùng: python -m app.set_license '<key>'")
    asyncio.run(_main(sys.argv[1]))
