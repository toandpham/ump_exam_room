#!/usr/bin/env bash
# Sao lưu hệ thống thi: DB (pg_dump gzip) + .env + backend/uploads (AD-75).
#
# Trước đây chỉ dump DB — KHÔNG ĐỦ để dựng lại máy mới: `encrypted_payload`
# (đề đã nạp) mã hoá bằng key dẫn xuất từ JWT_SECRET trong .env; ảnh thí sinh
# nằm ở backend/uploads. Mất 2 thứ đó thì restore DB xong vẫn không mở đề được.
#
# Cách dùng:
#   ./scripts/backup.sh [TARGET_DIR]
# Ví dụ (ra USB ngoài):
#   ./scripts/backup.sh /Volumes/EXAM_USB/backups
#
# Giữ lại 100 bản dump DB mới nhất; .env + uploads chép đè bản mới nhất mỗi lần.
# Khôi phục: ./scripts/restore.sh <file .sql.gz> — xem hướng dẫn trong đó.
set -euo pipefail

cd "$(dirname "$0")/.."

# Load DB credentials from .env if present.
POSTGRES_USER="exam"
POSTGRES_DB="exam_db"
[ -f .env ] && export $(grep -E '^(POSTGRES_USER|POSTGRES_DB)=' .env | xargs)

TARGET="${1:-./backups}"
mkdir -p "$TARGET"
TS=$(date +%Y%m%d_%H%M%S)
FILE="$TARGET/exam_db_${TS}.sql.gz"

docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$FILE"
echo "Backup written: $FILE ($(du -h "$FILE" | cut -f1))"

# .env (chứa JWT_SECRET — thiếu nó không giải mã được đề trong DB) + uploads
# (ảnh thí sinh + ảnh đề đã materialize). rsync nếu có (nhanh, incremental),
# không thì tar đè.
[ -f .env ] && cp .env "$TARGET/env.backup"
if [ -d backend/uploads ]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete backend/uploads/ "$TARGET/uploads/"
  else
    tar -czf "$TARGET/uploads.tar.gz" -C backend uploads
  fi
fi

# Retain the latest 100 DB dumps.
ls -1t "$TARGET"/exam_db_*.sql.gz 2>/dev/null | tail -n +101 | xargs -r rm -f
