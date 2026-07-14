#!/usr/bin/env bash
# ============================================================================
#  PHÁT HÀNH bản kiosk mới cho cơ chế tự-cập-nhật (AD-84).
#
#  Quy trình khi có thay đổi kiosk:
#    1. Sửa code + BUMP "version" trong exam-kiosk/package.json (vd 1.2.0 → 1.3.0)
#    2. ./release.sh          # build .exe → copy vào ../kiosk-release/ + latest.json
#    3. git add -A && git commit -m "release kiosk vX.Y.Z" && git push
#    4. Trên server thi:  ./update.sh   (kéo bản mới → server phát cho máy thi)
#    5. Máy thi lần khởi động kế TỰ tải + cài bản mới (trước khi thí sinh vào đề)
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"                       # exam-kiosk/

VERSION=$(node -p "require('./package.json').version")
echo "[release] Build kiosk v$VERSION (electron-builder NSIS ia32)…"
npm run dist

REL="../kiosk-release"
mkdir -p "$REL"
cp dist/UMP_ExamKiosk-Setup.exe "$REL/UMP_ExamKiosk-Setup.exe"

# Ghi + KÝ manifest (SHA-256 + chữ ký Ed25519 offline) — kiosk verify trước khi cài (AD-85).
node sign-release.js

echo "[release] ✅ kiosk-release/ đã cập nhật v$VERSION."
echo "  Tiếp:  git add -A && git commit -m \"release kiosk v$VERSION\" && git push"
echo "  Rồi trên SERVER thi:  ./update.sh"
