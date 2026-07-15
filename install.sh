#!/usr/bin/env bash
# ============================================================================
#  CÀI ĐẶT 1 LỆNH — Hệ thống thi trắc nghiệm offline (server Linux)
#
#  Cách dùng (Ubuntu/Debian, chạy quyền root):
#      git clone <repo-url> app_thi_thu
#      cd app_thi_thu
#      sudo ./install.sh
#
#  Script tự động:
#    1. Kiểm tra hệ điều hành + cài Docker Engine & Compose nếu thiếu
#    2. Sinh file .env với JWT secret + mật khẩu DB ngẫu nhiên (chỉ lần đầu)
#    3. Build + khởi động toàn bộ stack (Postgres/Redis/Backend/2 FE/Caddy)
#    4. Chạy migration DB + tạo tài khoản quản trị mặc định
#    5. In địa chỉ truy cập + tài khoản — sẵn sàng dùng ngay
#
#  Chạy lại script an toàn (idempotent): .env giữ nguyên, stack build lại.
# ============================================================================
set -euo pipefail

BOLD=$(tput bold 2>/dev/null || true); RESET=$(tput sgr0 2>/dev/null || true)
info()  { echo "${BOLD}[CÀI ĐẶT]${RESET} $*"; }
die()   { echo "${BOLD}[LỖI]${RESET} $*" >&2; exit 1; }

cd "$(dirname "$0")"

# ── 0. Điều kiện tiên quyết ──────────────────────────────────────────────────
[ "$(id -u)" -eq 0 ] || die "Cần quyền root — chạy:  sudo ./install.sh"
[ "$(uname -s)" = "Linux" ] || die "Script này dành cho server Linux (Ubuntu/Debian)."
command -v apt-get >/dev/null 2>&1 \
  || die "Không tìm thấy apt-get — hiện chỉ hỗ trợ Ubuntu/Debian."

# ── 1. Docker Engine + Compose ───────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  info "Docker chưa có — đang cài (script chính thức get.docker.com)…"
  apt-get update -qq
  apt-get install -y -qq curl ca-certificates >/dev/null
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
else
  info "Docker đã có: $(docker --version)"
fi
docker compose version >/dev/null 2>&1 \
  || { info "Cài docker compose plugin…"; apt-get install -y -qq docker-compose-plugin >/dev/null; }
info "Compose: $(docker compose version --short)"

# ── 2. Sinh .env (chỉ lần đầu — chạy lại KHÔNG ghi đè) ───────────────────────
if [ ! -f .env ]; then
  info "Tạo .env với secret ngẫu nhiên…"
  cp .env.example .env
  SECRET=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
  PGPASS=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')
  sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${SECRET}|" .env
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${PGPASS}|" .env
  sed -i "s|change_me_postgres|${PGPASS}|g" .env
  sed -i "s|^ENVIRONMENT=.*|ENVIRONMENT=production          # development \| production|" .env
  info "Đã tạo .env (JWT secret + mật khẩu DB ngẫu nhiên, ENVIRONMENT=production)."
else
  info ".env đã tồn tại — giữ nguyên."
fi

# ── 3. Build + khởi động stack ───────────────────────────────────────────────
info "Build + khởi động các dịch vụ (lần đầu có thể mất 5–10 phút)…"
docker compose up -d --build

# ── 4. Chờ backend khoẻ ──────────────────────────────────────────────────────
info "Chờ hệ thống sẵn sàng…"
for i in $(seq 1 120); do
  if curl -fsS http://localhost/health >/dev/null 2>&1; then break; fi
  [ "$i" -eq 120 ] && die "Backend không lên sau 4 phút — xem log:  docker compose logs backend"
  sleep 2
done
info "Backend đã khoẻ."

# ── 5. Migration DB + tài khoản mặc định (idempotent) ────────────────────────
info "Chạy migration cơ sở dữ liệu…"
docker compose exec -T backend alembic upgrade head

info "Tạo tài khoản quản trị mặc định (bỏ qua nếu đã có)…"
docker compose exec -T backend python - <<'PYEOF'
import asyncio
from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models import Admin
from app.models.enums import AdminRole
from app.core.security import hash_password

ACCOUNTS = [
    ("admin",    "admin123",   "Quản trị hệ thống",    AdminRole.SUPER_ADMIN.value),
    ("proctor1", "proctor123", "Chủ tịch hội đồng thi", AdminRole.PROCTOR.value),
]

async def main():
    async with AsyncSessionLocal() as s:
        for username, pw, name, role in ACCOUNTS:
            if await s.scalar(select(Admin).where(Admin.username == username)):
                print(f"  - {username}: đã tồn tại, bỏ qua")
                continue
            s.add(Admin(username=username, password_hash=hash_password(pw),
                        full_name=name, role=role, is_active=True))
            print(f"  - tạo {username} / {pw}")
        await s.commit()

asyncio.run(main())
PYEOF

# ── 6. Giấy phép (AD-81) ─────────────────────────────────────────────────────
# KHÔNG hỏi key khi cài. Cài xong TỰ dùng thử 90 ngày (backend đặt mốc installed_at
# ở startup). Muốn gia hạn về sau → nhập key ở trang Giấy phép (đăng nhập Quản trị)
# hoặc CLI: docker compose exec backend python -m app.set_license '<key>'
LICENSE_STATE=$(docker compose exec -T backend python - <<'PYEOF'
import asyncio
from app.services import license_service
from app.database import AsyncSessionLocal
async def main():
    async with AsyncSessionLocal() as db:
        st = await license_service.read_state(db)
        print(f"{st.status} {st.days_left if st.days_left is not None else ''}")
asyncio.run(main())
PYEOF
)
set -- $LICENSE_STATE
if [ "$1" = "trial" ]; then
  info "Giấy phép: đang dùng thử — còn ${2:-90} ngày. Gia hạn sau tại trang Giấy phép."
elif [ "$1" = "valid" ]; then
  info "Giấy phép: đang hoạt động — còn ${2:-?} ngày."
else
  info "⚠️  Giấy phép: $1 — vào trang Giấy phép (tài khoản Quản trị) để nhập key gia hạn."
fi

# ── 6b. Khoá giải mã đề (.qenc) ──────────────────────────────────────────────
# Không nhúng trong mã nguồn (repo công khai) → phải điền vào .env khi triển khai,
# nếu không thì KHÔNG nạp được đề thi (báo lỗi rõ ở trang Nạp đề).
if ! grep -qE '^QTI_SECRET=.+' .env 2>/dev/null; then
  echo
  echo "${BOLD}  ⚠️  CHƯA CÓ KHOÁ GIẢI MÃ ĐỀ (QTI_SECRET) — chưa nạp được đề thi.${RESET}"
  echo "      Xin nhà cung cấp chuỗi khoá, rồi chạy 2 lệnh sau (thay <KHOÁ>):"
  echo "        sed -i 's|^QTI_SECRET=.*|QTI_SECRET=<KHOÁ>|' .env"
  echo "        docker compose up -d backend"
fi

# ── 7. mDNS: quảng bá exam-server.local để KIOSK tự tìm server ───────────────
# Kiosk thi tìm server qua tên mDNS 'exam-server.local'. Linux mặc định không
# quảng bá mDNS → cài Avahi + đặt tên quảng bá = exam-server (KHÔNG đổi hostname
# hệ thống, chỉ đổi tên Avahi phát ra). Nếu switch mạng chặn multicast thì đặt IP
# tĩnh server vào kiosk.config.json (serverIp) — xem exam-kiosk/README.
if ! command -v avahi-daemon >/dev/null 2>&1; then
  info "Cài Avahi (mDNS) để kiosk tự tìm server…"
  apt-get install -y -qq avahi-daemon avahi-utils >/dev/null 2>&1 || true
fi
if [ -f /etc/avahi/avahi-daemon.conf ]; then
  if grep -qE '^[[:space:]]*#?[[:space:]]*host-name=' /etc/avahi/avahi-daemon.conf; then
    sed -i 's|^[[:space:]]*#\?[[:space:]]*host-name=.*|host-name=exam-server|' /etc/avahi/avahi-daemon.conf
  else
    sed -i '/^\[server\]/a host-name=exam-server' /etc/avahi/avahi-daemon.conf
  fi
  systemctl enable --now avahi-daemon >/dev/null 2>&1 || true
  systemctl restart avahi-daemon >/dev/null 2>&1 || true
  info "Avahi quảng bá 'exam-server.local' — kiosk tự tìm được server (nếu LAN cho phép mDNS)."
else
  info "⚠️  Không cấu hình được Avahi — đặt IP tĩnh server vào kiosk.config.json (serverIp)."
fi

# ── 8. Tổng kết ──────────────────────────────────────────────────────────────
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo
echo "${BOLD}==========================================================${RESET}"
echo "${BOLD}  ✅ CÀI ĐẶT HOÀN TẤT — hệ thống đang chạy${RESET}"
echo "${BOLD}==========================================================${RESET}"
echo
echo "  Quản trị     : http://${IP:-<IP-server>}/admin     (admin / admin123)"
echo "  Chủ tịch     : http://${IP:-<IP-server>}/chutich   (proctor1 / proctor123)"
echo "  Giám thị     : http://${IP:-<IP-server>}/giamthi   (giamthi1..10 — chủ tịch cấp PIN)"
echo "  Thí sinh     : http://${IP:-<IP-server>}/thisinh"
echo
echo "  ⚠️  ĐỔI NGAY mật khẩu mặc định trước khi tổ chức thi thật."
echo "  ℹ️  Đang dùng thử 90 ngày kể từ lúc cài. Gia hạn: trang Giấy phép (tài khoản Quản trị)."
echo "  ℹ️  Kiosk tìm server qua 'exam-server.local' (Avahi). Nếu mạng chặn mDNS: đặt"
echo "      serverIp=\"${IP:-<IP-server>}\" trong kiosk.config.json (xem exam-kiosk/README)."
echo "  Lệnh thường dùng:"
echo "    docker compose ps               # trạng thái dịch vụ"
echo "    docker compose logs -f backend  # xem log"
echo "    docker compose down             # dừng hệ thống"
echo "    ./update.sh                     # CẬP NHẬT/sửa lỗi: git pull + build + restart"
echo
