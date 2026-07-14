#!/usr/bin/env bash
# Khôi phục DB thi từ bản sao lưu của backup.sh (AD-75).
#
#   ./scripts/restore.sh <đường dẫn exam_db_YYYYmmdd_HHMMSS.sql.gz>
#
# LƯU Ý:
# - Script DROP toàn bộ DB hiện tại rồi đổ lại từ dump (pg_dump không --clean
#   nên đổ chồng lên DB có sẵn sẽ lỗi duplicate hàng loạt — vì vậy phải drop).
# - Nếu restore sang MÁY MỚI: chép `env.backup` về `.env` TRƯỚC khi chạy
#   (JWT_SECRET phải khớp thì mới giải mã được đề trong DB), và chép thư mục
#   `uploads/` về `backend/uploads/`.
# - Backend được stop trong lúc restore rồi bật lại.
set -euo pipefail

cd "$(dirname "$0")/.."

DUMP="${1:?Cách dùng: ./scripts/restore.sh <file .sql.gz>}"
[ -f "$DUMP" ] || { echo "[LỖI] Không thấy file: $DUMP" >&2; exit 1; }

POSTGRES_USER="exam"
POSTGRES_DB="exam_db"
[ -f .env ] && export $(grep -E '^(POSTGRES_USER|POSTGRES_DB)=' .env | xargs)

echo "== Dừng backend (giữ Postgres chạy) =="
docker compose stop backend

echo "== Drop + tạo lại DB ${POSTGRES_DB} =="
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d postgres \
  -c "DROP DATABASE IF EXISTS ${POSTGRES_DB} WITH (FORCE);" \
  -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

echo "== Đổ dữ liệu từ $DUMP =="
gunzip -c "$DUMP" | docker compose exec -T postgres psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"

echo "== Bật lại backend =="
docker compose start backend

echo "XONG. Kiểm tra: curl http://localhost/api/health && đăng nhập thử."
