#!/bin/sh
# ============================================================================
#  Điểm khởi động backend: TỰ TẠO/NÂNG CẤP BẢNG rồi mới phục vụ.
#
#  Vì sao cần (sự cố cài đặt tại trường 27-07): cài mới → DB trống → backend
#  khởi động, lifespan truy vấn bảng chưa tồn tại → app chết → healthcheck fail
#  → Caddy (depends_on: service_healthy) không start → `docker compose up -d`
#  trả lỗi → install.sh dừng ngay ở đó (set -e) → BƯỚC MIGRATION PHÍA SAU KHÔNG
#  BAO GIỜ CHẠY → kẹt vĩnh viễn, không cài được.
#
#  Chạy alembic Ở ĐÂY phá vòng luẩn quẩn đó: bảng luôn có trước khi app phục vụ,
#  không phụ thuộc thứ tự lệnh trong script cài. Idempotent — đã đủ bảng thì
#  alembic không làm gì. Chạy MỘT lần trước khi spawn uvicorn nên không có race
#  giữa các worker.
# ============================================================================
set -e

echo "[backend] Chờ cơ sở dữ liệu…"
# Postgres đã có healthcheck ở compose, nhưng thêm vòng chờ ngắn cho chắc (máy
# yếu/khởi động nguội có thể chậm hơn healthcheck một nhịp).
for i in $(seq 1 60); do
  if python -c "
import asyncio, sys
from app.database import engine
from sqlalchemy import text
async def m():
    async with engine.connect() as c:
        await c.execute(text('SELECT 1'))
asyncio.run(m())
" >/dev/null 2>&1; then
    break
  fi
  [ "$i" -eq 60 ] && { echo "[backend] LỖI: không kết nối được cơ sở dữ liệu sau 2 phút."; exit 1; }
  sleep 2
done

echo "[backend] Cập nhật cấu trúc cơ sở dữ liệu (alembic upgrade head)…"
alembic upgrade head

echo "[backend] Khởi động máy chủ ứng dụng…"
exec "$@"
