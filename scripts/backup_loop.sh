#!/usr/bin/env bash
# Continuously back up the database during an exam (e.g. to an external USB).
#
# Usage:
#   ./scripts/backup_loop.sh [TARGET_DIR] [INTERVAL_SECONDS]
# Example:
#   ./scripts/backup_loop.sh /Volumes/EXAM_USB/backups 60
#
# Stop with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")"

# AD-75: mặc định 300s (trước là 60s) — pg_dump mỗi phút kéo cả blob
# encrypted_payload (~100MB+/buổi) là tải I/O vô ích đúng lúc thi.
TARGET="${1:-../backups}"
INTERVAL="${2:-300}"

echo "Backing up every ${INTERVAL}s to ${TARGET} (Ctrl+C to stop)…"
while true; do
  ./backup.sh "$TARGET" || echo "backup failed at $(date)"
  sleep "$INTERVAL"
done
