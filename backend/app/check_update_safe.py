"""CLI cho scripts/auto-update.sh hỏi: có được tự cập nhật lúc này không? (AD-87)

    docker compose exec -T backend python -m app.check_update_safe

Thoát 0 = AN TOÀN (không kỳ thi nào đang/sắp diễn ra).
Thoát 1 = KHÔNG an toàn, in lý do ra stdout.
Thoát 2 = không kiểm được (DB lỗi…) → gọi bên ngoài phải coi như KHÔNG an toàn.
"""

from __future__ import annotations

import asyncio
import sys

from app.database import AsyncSessionLocal
from app.maintenance import update_safety


async def _main() -> int:
    async with AsyncSessionLocal() as db:
        safe, reason = await update_safety(db)
    print(reason)
    return 0 if safe else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()))
    except Exception as exc:  # noqa: BLE001 — không kiểm được thì coi như KHÔNG an toàn
        print(f"không kiểm tra được trạng thái kỳ thi: {exc}")
        sys.exit(2)
