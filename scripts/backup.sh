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
# Giữ .env + uploads (chép đè bản mới nhất mỗi lần) + N bản dump DB gần nhất.
# Khôi phục: ./scripts/restore.sh <file .sql.gz> — xem hướng dẫn trong đó.
#
# Giới hạn chỗ chứa (quan trọng khi chạy tự động theo hẹn giờ): mỗi dump kéo cả
# `encrypted_payload` (đề đã nạp, có thể ~100MB/buổi) nên vài chục bản là đầy đĩa
# → Postgres hết chỗ ghi = SẬP GIỮA BUỔI THI. Vì vậy có 3 lớp chặn:
#   BACKUP_KEEP     số bản dump giữ lại        (mặc định 48 = 8 giờ nếu hẹn 10 phút)
#   BACKUP_MAX_MB   trần dung lượng thư mục    (mặc định 10 GB)
#   dừng hẳn nếu đĩa còn trống < BACKUP_MIN_FREE_MB (mặc định 2 GB)
set -euo pipefail

cd "$(dirname "$0")/.."

# Load DB credentials from .env if present.
POSTGRES_USER="exam"
POSTGRES_DB="exam_db"
[ -f .env ] && export $(grep -E '^(POSTGRES_USER|POSTGRES_DB)=' .env | xargs)

KEEP="${BACKUP_KEEP:-48}"
MAX_MB="${BACKUP_MAX_MB:-10240}"
MIN_FREE_MB="${BACKUP_MIN_FREE_MB:-2048}"

TARGET="${1:-./backups}"
mkdir -p "$TARGET"

# Thà KHÔNG sao lưu còn hơn làm đầy đĩa (đầy đĩa = Postgres không ghi được nữa).
FREE_MB=$(df -Pm "$TARGET" 2>/dev/null | awk 'NR==2{print $4}')
if [ -n "${FREE_MB:-}" ] && [ "$FREE_MB" -lt "$MIN_FREE_MB" ]; then
  echo "[SAO LƯU] BỎ QUA: đĩa chỉ còn ${FREE_MB}MB trống (< ${MIN_FREE_MB}MB). Dọn bớt $TARGET." >&2
  exit 0
fi

TS=$(date +%Y%m%d_%H%M%S)
FILE="$TARGET/exam_db_${TS}.sql.gz"

# Dump hỏng giữa chừng (Postgres đang tắt, hết chỗ…) không được để lại file cụt —
# người vận hành sẽ tưởng đó là bản sao lưu dùng được.
if ! docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$FILE"; then
  rm -f "$FILE"
  echo "[SAO LƯU] LỖI: pg_dump thất bại — không tạo được bản sao lưu." >&2
  exit 1
fi
echo "Backup written: $FILE ($(du -h "$FILE" | cut -f1))"

# .env (chứa JWT_SECRET — thiếu nó không giải mã được đề trong DB) + uploads
# (ảnh thí sinh + ảnh đề đã materialize). rsync nếu có (nhanh, incremental),
# không thì tar đè.
if [ -f .env ]; then
  cp .env "$TARGET/env.backup"
  chmod 600 "$TARGET/env.backup"   # chứa JWT_SECRET
fi
if [ -d backend/uploads ]; then
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete backend/uploads/ "$TARGET/uploads/"
  else
    tar -czf "$TARGET/uploads.tar.gz" -C backend uploads
  fi
fi

# ── Dọn bớt: theo SỐ BẢN trước, rồi theo DUNG LƯỢNG ──────────────────────────
ls -1t "$TARGET"/exam_db_*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f

while [ "$(ls -1 "$TARGET"/exam_db_*.sql.gz 2>/dev/null | wc -l)" -gt 1 ]; do
  USED_MB=$(du -sm "$TARGET" 2>/dev/null | cut -f1)
  [ -n "${USED_MB:-}" ] && [ "$USED_MB" -gt "$MAX_MB" ] || break
  OLDEST=$(ls -1t "$TARGET"/exam_db_*.sql.gz 2>/dev/null | tail -1)
  [ -n "$OLDEST" ] || break
  rm -f "$OLDEST"
  echo "[SAO LƯU] Vượt trần ${MAX_MB}MB — đã xoá bản cũ nhất: $(basename "$OLDEST")"
done
