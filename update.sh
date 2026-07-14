#!/usr/bin/env bash
# ============================================================================
#  CẬP NHẬT 1 LỆNH — kéo bản sửa lỗi mới nhất qua git rồi áp vào hệ thống.
#
#  Dùng khi có bản vá:
#      ./update.sh            # cập nhật lên bản mới nhất
#      ./update.sh --force    # vẫn cập nhật dù đang có kỳ thi chạy (cẩn thận!)
#
#  Chạy: git pull → build lại image → migration DB → khởi động lại → kiểm tra.
#  Chạy được cả macOS (OrbStack) lẫn Linux. Trên Linux nếu docker cần quyền:
#      sudo ./update.sh
#
#  AN TOÀN: tự CHẶN khi đang có thí sinh thi (build+restart sẽ làm văng họ) —
#  trừ khi thêm --force. KHÔNG đụng .env, KHÔNG xoá dữ liệu.
# ============================================================================
set -euo pipefail

BOLD=$(tput bold 2>/dev/null || true); RESET=$(tput sgr0 2>/dev/null || true)
info() { echo "${BOLD}[CẬP NHẬT]${RESET} $*"; }
die()  { echo "${BOLD}[LỖI]${RESET} $*" >&2; exit 1; }

cd "$(dirname "$0")"
FORCE=0; [ "${1:-}" = "--force" ] && FORCE=1

command -v git >/dev/null 2>&1 || die "Chưa cài git."
command -v docker >/dev/null 2>&1 || die "Chưa cài Docker."
[ -d .git ] || die "Thư mục này không phải git repo — không cập nhật qua git được."
[ -f docker-compose.yml ] || die "Không thấy docker-compose.yml — sai thư mục cài đặt."

# ── 1. Chốt an toàn: không cập nhật khi đang có kỳ thi chạy ───────────────────
if docker compose ps --status running 2>/dev/null | grep -q backend; then
  RUNNING=$(docker compose exec -T backend python - <<'PYEOF' 2>/dev/null || true
import asyncio
from sqlalchemy import select, func
from app.database import AsyncSessionLocal
from app.models import ExamSession
from app.models.enums import SessionStatus
async def m():
    async with AsyncSessionLocal() as db:
        n = await db.scalar(select(func.count()).select_from(ExamSession)
                            .where(ExamSession.status == SessionStatus.IN_PROGRESS.value))
        print(n)
asyncio.run(m())
PYEOF
)
  RUNNING=$(echo "$RUNNING" | tr -dc '0-9')
  if [ -n "$RUNNING" ] && [ "$RUNNING" -gt 0 ] 2>/dev/null; then
    if [ "$FORCE" -eq 1 ]; then
      info "⚠️  Đang có $RUNNING thí sinh THI — vẫn cập nhật vì --force."
    else
      die "Đang có $RUNNING thí sinh đang thi. Cập nhật sẽ khởi động lại và làm VĂNG họ.
      → Chờ thi xong rồi chạy lại, hoặc (nếu chắc chắn):  ./update.sh --force"
    fi
  fi
fi

# ── 2. Kéo code mới (chạy git theo CHỦ SỞ HỮU repo — đúng khoá SSH + đúng quyền file) ──
OWNER=$(ls -ld .git | awk '{print $3}')
ME=$(id -un)
run_git() {
  if [ "$ME" != "$OWNER" ] && command -v sudo >/dev/null 2>&1; then
    sudo -u "$OWNER" git "$@"
  else
    git "$@"
  fi
}
git config --global --add safe.directory "$PWD" >/dev/null 2>&1 || true

BRANCH=$(run_git rev-parse --abbrev-ref HEAD)
BEFORE=$(run_git rev-parse HEAD)
info "Nhánh '$BRANCH' — đang kéo bản mới nhất từ máy chủ git…"
run_git pull --ff-only \
  || die "git pull thất bại (có thể do đã sửa file cục bộ, hoặc nhánh bị lệch).
      Kiểm tra:  git status   /   git log --oneline -5"
AFTER=$(run_git rev-parse HEAD)

if [ "$BEFORE" = "$AFTER" ]; then
  info "Đã là bản mới nhất ($(run_git rev-parse --short HEAD)) — không có gì để cập nhật."
  exit 0
fi

info "Có bản mới. Các thay đổi sẽ áp dụng:"
run_git log --oneline "$BEFORE..$AFTER" | sed 's/^/    /'

# ── 3. Build lại + khởi động lại (áp bản vá) ─────────────────────────────────
info "Build lại image + khởi động lại các dịch vụ…"
docker compose up -d --build

# ── 4. Chờ backend khoẻ ──────────────────────────────────────────────────────
info "Chờ hệ thống sẵn sàng…"
for i in $(seq 1 120); do
  curl -fsS http://localhost/health >/dev/null 2>&1 && break
  [ "$i" -eq 120 ] && die "Backend không lên sau 4 phút — xem log:  docker compose logs backend"
  sleep 2
done

# ── 5. Migration DB (idempotent — không có gì mới thì bỏ qua) ────────────────
info "Chạy migration cơ sở dữ liệu…"
docker compose exec -T backend alembic upgrade head

info "✅ CẬP NHẬT XONG — hệ thống đang chạy bản $(run_git rev-parse --short HEAD)."
echo "   (Nếu vừa sửa app THÍ SINH hoặc KIOSK: bảo thí sinh tải lại trang / phát lại file kiosk mới.)"
