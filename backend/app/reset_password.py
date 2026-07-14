"""CLI: reset an admin's password from the server console.

Safety net for a forgotten super_admin password when no other super_admin can
reset it from the UI. Run on the Mac Mini:

    docker compose exec backend python -m app.reset_password <username> <new-password>
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from app.core.security import hash_password
from app.database import AsyncSessionLocal
from app.models import Admin


async def _run(username: str, new_password: str) -> int:
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(Admin).where(Admin.username == username))
        if admin is None:
            print(f"[!] Không tìm thấy tài khoản '{username}'.")
            return 1
        admin.password_hash = hash_password(new_password)
        await db.commit()
        print(f"[OK] Đã đặt lại mật khẩu cho '{username}'.")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset an admin's password.")
    parser.add_argument("username")
    parser.add_argument("password", help="New password (min 6 chars).")
    args = parser.parse_args()
    if len(args.password) < 6:
        print("[!] Mật khẩu tối thiểu 6 ký tự.")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(_run(args.username, args.password)))


if __name__ == "__main__":
    main()
