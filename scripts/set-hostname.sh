#!/usr/bin/env bash
# Pin the Mac's mDNS hostname to "exam-server" so the system is always
# reachable as http(s)://exam-server.local from any client on the same LAN.
# Idempotent — safe to re-run after re-imaging or moving to a new network.
#
# Requires sudo (one-time).  Usage:  sudo ./scripts/set-hostname.sh
set -euo pipefail

NAME="${1:-exam-server}"

if [[ $EUID -ne 0 ]]; then
  echo "Cần sudo: sudo $0 ${NAME}" >&2
  exit 1
fi

echo "Đặt HostName + LocalHostName = ${NAME}"
scutil --set HostName       "${NAME}"
scutil --set LocalHostName  "${NAME}"
scutil --set ComputerName   "${NAME}"
dscacheutil -flushcache
killall -HUP mDNSResponder 2>/dev/null || true

sleep 1
echo
echo "Kết quả:"
echo "  HostName       = $(scutil --get HostName)"
echo "  LocalHostName  = $(scutil --get LocalHostName)"
echo "  ComputerName   = $(scutil --get ComputerName)"
echo
echo "→ Truy cập:  http://${NAME}.local/admin/   và   http://${NAME}.local/exam/"
echo "→ HTTPS:    https://${NAME}.local/admin/   (cert tự ký, lần đầu bỏ qua cảnh báo)"
