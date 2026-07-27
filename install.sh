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

# Dung lượng đĩa: build 2 image Node + Postgres/Redis/Caddy cần ~8 GB. Báo TRƯỚC
# thay vì để build chết giữa chừng với lỗi khó hiểu.
FREE_GB=$(df -BG --output=avail . 2>/dev/null | tail -1 | tr -dc '0-9')
if [ -n "${FREE_GB:-}" ] && [ "$FREE_GB" -lt 8 ]; then
  die "Chỉ còn ${FREE_GB} GB trống — cần tối thiểu 8 GB để build. Dọn đĩa rồi chạy lại."
fi

# ── 1. Gói phụ thuộc trên host + Docker Engine/Compose ───────────────────────
# curl: dùng ở bước chờ backend khoẻ · python3: watcher cập-nhật-qua-web ghi
# trạng thái · git: update.sh kéo bản vá. Trước đây curl chỉ được cài trong nhánh
# "chưa có Docker" → máy đã cài sẵn Docker mà thiếu curl thì script treo 4 phút
# rồi báo nhầm là "backend không lên".
MISSING=""
for pkg in curl python3 git ca-certificates; do
  command -v "${pkg}" >/dev/null 2>&1 || MISSING="$MISSING $pkg"
done
[ -e /etc/ssl/certs/ca-certificates.crt ] || MISSING="$MISSING ca-certificates"
if [ -n "$MISSING" ]; then
  info "Cài gói còn thiếu trên máy chủ:$MISSING"
  apt-get update -qq
  # shellcheck disable=SC2086
  apt-get install -y -qq $MISSING >/dev/null
fi

if ! command -v docker >/dev/null 2>&1; then
  info "Docker chưa có — đang cài (script chính thức get.docker.com)…"
  curl -fsSL https://get.docker.com | sh
else
  info "Docker đã có: $(docker --version)"
fi
# Bật khởi động cùng máy KỂ CẢ khi Docker đã cài sẵn — nếu không, sau khi cúp
# điện/reboot thì Docker không chạy và cả hệ thống thi im lặng không lên.
systemctl enable --now docker >/dev/null 2>&1 || true
docker compose version >/dev/null 2>&1 \
  || { info "Cài docker compose plugin…"; apt-get install -y -qq docker-compose-plugin >/dev/null; }
info "Compose: $(docker compose version --short)"

# ── 1b. Cổng 80/443 phải trống ───────────────────────────────────────────────
# Nhiều trường đã có sẵn web server (Apache/nginx/webhost) giữ cổng 80 → Caddy
# không bind được và compose báo "port is already allocated" ở giữa chừng. Bắt
# TRƯỚC, kèm tên tiến trình đang giữ cổng để IT xử lý.
if ! docker compose ps --status running 2>/dev/null | grep -q caddy; then
  for P in 80 443; do
    HOLDER=$(ss -ltnp 2>/dev/null | awk -v p=":$P\$" '$4 ~ p {print $NF; exit}')
    [ -n "$HOLDER" ] && die "Cổng $P đang bị chiếm bởi: $HOLDER
      Hệ thống thi cần cổng 80 (và 443). Hãy dừng dịch vụ đó rồi chạy lại:
        sudo systemctl stop apache2   # hoặc nginx / dịch vụ web đang chạy
        sudo systemctl disable apache2"
  done
fi

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
# .env chứa JWT_SECRET (khoá mã hoá đề lưu trong DB dẫn xuất từ đây) + mật khẩu
# CSDL → không để người dùng khác trên máy chủ đọc được.
chmod 600 .env

# ── 2b. Chỉnh tài nguyên theo cấu hình máy chủ ────────────────────────────────
# Các con số mặc định trong docker-compose.yml được chọn cho máy 24 GB RAM/10 nhân
# (máy thi gốc). Máy chủ nhà trường nhỏ hơn mà vẫn dùng số đó thì Postgres + 6
# worker sẽ tranh nhau RAM → swap → chậm hoặc bị OOM-kill giữa buổi thi. Ghi mức
# phù hợp vào .env (compose đọc, thiếu thì dùng mặc định cũ).
if ! grep -q '^UVICORN_WORKERS=' .env 2>/dev/null; then
  MEM_MB=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')
  CPUS=$(nproc 2>/dev/null || echo 2)
  MEM_MB=${MEM_MB:-8000}
  if   [ "$MEM_MB" -ge 16000 ]; then WORKERS=6; SHB=1GB;   CACHE=3GB; MAXC=600
  elif [ "$MEM_MB" -ge 8000  ]; then WORKERS=4; SHB=512MB; CACHE=2GB; MAXC=400
  else                               WORKERS=2; SHB=256MB; CACHE=1GB; MAXC=200
  fi
  [ "$WORKERS" -gt "$CPUS" ] && WORKERS=$CPUS
  [ "$WORKERS" -lt 2 ] && WORKERS=2
  {
    echo ""
    echo "# --- Tài nguyên máy chủ (install.sh tự đặt theo RAM ${MEM_MB}MB / ${CPUS} nhân) ---"
    echo "# Mỗi worker dùng tối đa 25 kết nối CSDL → WORKERS×25 phải < PG_MAX_CONNECTIONS."
    echo "UVICORN_WORKERS=${WORKERS}"
    echo "PG_MAX_CONNECTIONS=${MAXC}"
    echo "PG_SHARED_BUFFERS=${SHB}"
    echo "PG_EFFECTIVE_CACHE=${CACHE}"
  } >> .env
  info "Tài nguyên: ${MEM_MB}MB RAM / ${CPUS} nhân → ${WORKERS} worker, Postgres ${SHB}."
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
# Backend TỰ chạy alembic lúc khởi động (backend/entrypoint.sh) nên tới đây bảng
# đã có sẵn — giữ lệnh này làm lưới an toàn, chạy lại không hại gì.
info "Kiểm tra cấu trúc cơ sở dữ liệu…"
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

# ── 7b. Watcher cập nhật từ trang Quản trị (AD-89) ───────────────────────────
# Cho phép super_admin bấm "Cập nhật" ngay trong web — không cần SSH. Watcher chạy
# nền trên host, nhận yêu cầu qua file backend/update_request.flag, chạy ./update.sh
# (vẫn chặn khi đang thi) và ghi tiến trình cho trang admin đọc.
if command -v systemctl >/dev/null 2>&1; then
  cat > /etc/systemd/system/exam-update-watcher.service <<UNIT
[Unit]
Description=Nhan yeu cau cap nhat tu trang Quan tri
After=docker.service
[Service]
WorkingDirectory=${PWD}
ExecStart=${PWD}/scripts/update-watcher.sh
Restart=always
RestartSec=10
[Install]
WantedBy=multi-user.target
UNIT
  chmod +x "${PWD}/scripts/update-watcher.sh" 2>/dev/null || true
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl enable --now exam-update-watcher.service >/dev/null 2>&1 \
    && info "Cập nhật qua web: BẬT (trang Quản trị → Cập nhật)." \
    || info "⚠️  Không bật được watcher cập nhật — dùng ./update.sh thủ công."
else
  info "Không có systemd — cập nhật qua web không hoạt động; dùng ./update.sh."
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
