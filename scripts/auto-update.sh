#!/usr/bin/env bash
# ============================================================================
#  TỰ ĐỘNG CẬP NHẬT máy chủ thi khi có bản vá mới (AD-87).
#
#  Chạy định kỳ (systemd timer, xem install.sh). Mỗi lần chạy sẽ TỰ THOÁT NGAY
#  nếu chưa hội đủ điều kiện an toàn — chỉ thực sự cập nhật khi chắc chắn không
#  đụng tới kỳ thi nào.
#
#  Vì sao phải khắt khe: cập nhật = build lại image (5–10 phút, ngốn CPU/RAM) +
#  chạy migration DB, mà KHÔNG có ai đứng đó để cứu nếu hỏng. Làm nhầm lúc là
#  sập cả phòng thi.
#
#  Ba lớp an toàn:
#    1. GUARD  — khung giờ đêm + không kỳ thi nào đang/sắp diễn ra (app.check_update_safe)
#    2. BACKUP — sao lưu DB trước khi động vào bất cứ thứ gì
#    3. ROLLBACK — hỏng thì tự quay về commit cũ + phục hồi DB
#
#  Nhật ký: logs/auto-update.log (xem để biết nó đã làm gì / vì sao bỏ qua).
#  Tắt tự động: sudo systemctl disable --now exam-autoupdate.timer
# ============================================================================
set -uo pipefail

cd "$(dirname "$0")/.."
REPO="$PWD"
LOG_DIR="$REPO/logs"
LOG="$LOG_DIR/auto-update.log"
BACKUP_DIR="$REPO/backups/auto-update"
mkdir -p "$LOG_DIR" "$BACKUP_DIR"

log() { echo "[$(date '+%F %T')] $*" >> "$LOG"; }
skip() { log "BỎ QUA: $*"; exit 0; }
fail() { log "LỖI: $*"; exit 1; }

# ── 1. Khung giờ đêm ─────────────────────────────────────────────────────────
# Chỉ 02:00–04:00. Kể cả guard dữ liệu có sót thì cũng không ai thi giờ này.
HOUR=$(date +%H)
if [ "${FORCE_WINDOW:-0}" != "1" ]; then
  [ "$HOUR" -ge 2 ] && [ "$HOUR" -lt 4 ] || skip "ngoài khung giờ cho phép (02:00–04:00), giờ hiện tại ${HOUR}h"
fi

# ── 2. Có bản vá mới không? ──────────────────────────────────────────────────
command -v git >/dev/null 2>&1 || skip "không có git"
[ -d .git ] || skip "không phải git repo"

OWNER=$(ls -ld .git | awk '{print $3}')
ME=$(id -un)
run_git() {
  if [ "$ME" != "$OWNER" ] && command -v sudo >/dev/null 2>&1; then
    sudo -u "$OWNER" git "$@"
  else
    git "$@"
  fi
}
git config --global --add safe.directory "$REPO" >/dev/null 2>&1 || true

run_git fetch --quiet origin || skip "không kéo được git (mất mạng?) — thử lại lần sau"
BEFORE=$(run_git rev-parse HEAD)
REMOTE=$(run_git rev-parse '@{u}' 2>/dev/null) || skip "nhánh không theo dõi remote"
[ "$BEFORE" != "$REMOTE" ] || exit 0    # đã mới nhất — im lặng, không ghi log cho đỡ rác

log "Phát hiện bản vá mới: ${BEFORE:0:7} → ${REMOTE:0:7}"

# ── 3. GUARD: có kỳ thi nào đang/sắp diễn ra không? ──────────────────────────
docker compose ps --status running 2>/dev/null | grep -q backend \
  || skip "backend không chạy — không kiểm được trạng thái kỳ thi"

REASON=$(docker compose exec -T backend python -m app.check_update_safe 2>&1)
RC=$?
[ "$RC" -eq 0 ] || skip "chưa an toàn — $REASON"
log "Guard OK: $REASON"

# ── 4. BACKUP trước khi động vào gì ──────────────────────────────────────────
STAMP=$(date +%Y%m%d-%H%M%S)
DUMP="$BACKUP_DIR/pre-update-$STAMP.sql.gz"
if ! docker compose exec -T postgres pg_dump -U exam exam_db 2>/dev/null | gzip > "$DUMP"; then
  rm -f "$DUMP"
  fail "sao lưu DB thất bại → KHÔNG cập nhật (không có đường lùi thì không liều)"
fi
[ -s "$DUMP" ] || { rm -f "$DUMP"; fail "file sao lưu rỗng → KHÔNG cập nhật"; }
log "Đã sao lưu DB: $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1))"
# giữ 10 bản gần nhất
ls -1t "$BACKUP_DIR"/pre-update-*.sql.gz 2>/dev/null | tail -n +11 | xargs -r rm -f

# ── 5. Cập nhật ──────────────────────────────────────────────────────────────
rollback() {
  log "!!! CẬP NHẬT HỎNG — đang quay về bản cũ ${BEFORE:0:7}"
  run_git reset --hard "$BEFORE" >/dev/null 2>&1
  docker compose up -d --build >/dev/null 2>&1
  gunzip -c "$DUMP" | docker compose exec -T postgres psql -U exam -d exam_db >/dev/null 2>&1 \
    && log "đã phục hồi DB từ $(basename "$DUMP")" \
    || log "PHỤC HỒI DB THẤT BẠI — cần người xử lý, bản sao ở $DUMP"
  for i in $(seq 1 60); do
    curl -fsS http://localhost/api/health >/dev/null 2>&1 && { log "đã quay về bản cũ, hệ thống chạy lại OK"; exit 1; }
    sleep 2
  done
  log "QUAY VỀ BẢN CŨ RỒI MÀ HỆ THỐNG VẪN KHÔNG LÊN — CẦN NGƯỜI XỬ LÝ GẤP"
  exit 1
}

log "Bắt đầu cập nhật…"
run_git pull --ff-only --quiet || fail "git pull thất bại (sửa file cục bộ?) — không đụng gì thêm"
docker compose up -d --build >/dev/null 2>&1 || rollback

log "Chờ backend khoẻ…"
OK=0
for i in $(seq 1 120); do
  curl -fsS http://localhost/api/health >/dev/null 2>&1 && { OK=1; break; }
  sleep 2
done
[ "$OK" -eq 1 ] || rollback

docker compose exec -T backend alembic upgrade head >/dev/null 2>&1 || rollback

# Kiểm lần cuối: sau migration hệ thống còn sống không?
curl -fsS http://localhost/api/health >/dev/null 2>&1 || rollback

AFTER=$(run_git rev-parse HEAD)
log "✅ CẬP NHẬT XONG: ${BEFORE:0:7} → ${AFTER:0:7}"
run_git log --oneline "$BEFORE..$AFTER" 2>/dev/null | sed 's/^/    /' >> "$LOG"
