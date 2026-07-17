#!/usr/bin/env bash
# ============================================================================
#  WATCHER cập nhật từ trang Quản trị (AD-89) — chạy nền trên HOST (systemd).
#
#  Vòng lặp mỗi 15 giây:
#    - Thấy backend/update_request.flag (trang Quản trị bấm "Cập nhật")
#        → xoá flag → chạy ./update.sh (vẫn giữ chốt chặn "đang có thí sinh thi")
#        → ghi tiến trình/kết quả vào backend/update_state.json cho trang admin đọc.
#    - Định kỳ (10 phút) git fetch để biết "có bản mới không" → cũng ghi vào state.
#
#  Backend trong container KHÔNG có quyền gì thêm — chỉ ghi flag + đọc state qua
#  bind-mount. Mọi quyền git/build/migrate nằm ở đây (host).
#
#  Chạy thử 1 vòng (không lặp): ONCE=1 ./scripts/update-watcher.sh
#  Nhật ký cập nhật: logs/webupdate.log
# ============================================================================
set -uo pipefail

cd "$(dirname "$0")/.."
REPO="$PWD"
FLAG="$REPO/backend/update_request.flag"
STATE="$REPO/backend/update_state.json"
LOG_DIR="$REPO/logs"
LOG="$LOG_DIR/webupdate.log"
mkdir -p "$LOG_DIR"

FETCH_EVERY=600   # giây — nhịp git fetch kiểm bản mới
LOOP_EVERY=15     # giây — nhịp kiểm flag
last_fetch=0

OWNER=$(ls -ld .git 2>/dev/null | awk '{print $3}')
ME=$(id -un)
run_git() {
  if [ -n "$OWNER" ] && [ "$ME" != "$OWNER" ] && command -v sudo >/dev/null 2>&1; then
    sudo -u "$OWNER" git "$@"
  else
    git "$@"
  fi
}
git config --global --add safe.directory "$REPO" >/dev/null 2>&1 || true

# Ghi state JSON an toàn (python3 lo escape) — trang Quản trị đọc file này.
# $1=state  $2=message  (local/remote/update_available lấy từ biến toàn cục)
LOCAL=""; REMOTE=""; CHECKED_AT=""; STARTED_AT=""; FINISHED_AT=""
write_state() {
  S="$1" MSG="${2:-}" LOCAL="$LOCAL" REMOTE="$REMOTE" CHECKED_AT="$CHECKED_AT" \
  STARTED_AT="$STARTED_AT" FINISHED_AT="$FINISHED_AT" LOG_FILE="$LOG" OUT="$STATE" \
  python3 - <<'PYEOF'
import json, os, re
from datetime import datetime, timezone

_ansi = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\(B|\x0f")  # mã màu tput/ANSI → bỏ

log_tail = []
try:
    with open(os.environ["LOG_FILE"], encoding="utf-8", errors="replace") as f:
        log_tail = [_ansi.sub("", l).rstrip() for l in f.readlines()[-15:]]
except OSError:
    pass
local, remote = os.environ["LOCAL"], os.environ["REMOTE"]
state = {
    "state": os.environ["S"],
    "message": os.environ["MSG"] or None,
    "local": local or None,
    "remote": remote or None,
    "update_available": bool(local and remote and local != remote),
    "checked_at": os.environ["CHECKED_AT"] or None,
    "started_at": os.environ["STARTED_AT"] or None,
    "finished_at": os.environ["FINISHED_AT"] or None,
    "log_tail": log_tail,
    "written_at": datetime.now(timezone.utc).isoformat(),
}
tmp = os.environ["OUT"] + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(state, f, ensure_ascii=False)
os.replace(tmp, os.environ["OUT"])
PYEOF
}

refresh_heads() {
  LOCAL=$(run_git rev-parse --short HEAD 2>/dev/null || echo "")
  REMOTE=$(run_git rev-parse --short '@{u}' 2>/dev/null || echo "")
}

now_iso() { date -u +%Y-%m-%dT%H:%M:%S+00:00; }

LAST_STATE="idle"; LAST_MSG=""

while true; do
  now=$(date +%s)

  # Kiểm bản mới định kỳ (hoặc ngay khi có yêu cầu, để so đúng bản nhất).
  if [ $((now - last_fetch)) -ge $FETCH_EVERY ] || [ -f "$FLAG" ]; then
    run_git fetch --quiet origin 2>/dev/null && CHECKED_AT=$(now_iso)
    last_fetch=$now
  fi
  refresh_heads

  if [ -f "$FLAG" ]; then
    rm -f "$FLAG"
    STARTED_AT=$(now_iso); FINISHED_AT=""
    echo "" >> "$LOG"
    echo "===== [$(date '+%F %T')] Cập nhật theo yêu cầu từ trang Quản trị =====" >> "$LOG"
    write_state running "Đang cập nhật — hệ thống sẽ gián đoạn vài phút."
    if ./update.sh >> "$LOG" 2>&1; then
      refresh_heads
      FINISHED_AT=$(now_iso)
      LAST_STATE="done"; LAST_MSG="Cập nhật xong."
    else
      refresh_heads
      FINISHED_AT=$(now_iso)
      # update.sh tự chặn khi đang thi / pull fail… — lý do nằm trong log_tail.
      LAST_STATE="failed"; LAST_MSG="Cập nhật không chạy — xem chi tiết bên dưới."
    fi
    write_state "$LAST_STATE" "$LAST_MSG"
  else
    # Nhịp sống: trang Quản trị nhìn written_at để biết watcher còn chạy.
    write_state "$LAST_STATE" "$LAST_MSG"
  fi

  [ "${ONCE:-0}" = "1" ] && exit 0
  sleep $LOOP_EVERY
done
