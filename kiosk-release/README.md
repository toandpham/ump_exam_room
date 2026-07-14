# kiosk-release/ — bản kiosk server phát cho máy thi (AD-84)

Caddy phát thư mục này tại `http://<server>/kiosk/*`. Kiosk trên máy thi lúc khởi
động (trước khi thí sinh vào đề) đọc `latest.json`, nếu version mới hơn bản đang chạy
thì tải file `.exe` về + cài im lặng + khởi động lại.

- `latest.json` — `{ "version", "file", "sha256" }`
- `latest.json.sig` — chữ ký Ed25519 (base64url) trên đúng bytes `latest.json`. Kiosk verify
  bằng khoá công khai nhúng sẵn TRƯỚC khi tin (AD-85) → LAN attacker không giả được bản cập nhật.
- `UMP_ExamKiosk-Setup.exe` — file cài NSIS (commit vào git để `update.sh` kéo về server).

**KHÔNG sửa tay** thư mục này (sửa `latest.json` mà không ký lại → kiosk từ chối) — chạy
`exam-kiosk/release.sh` (build + ghi + KÝ) rồi `git commit && git push`, trên server `./update.sh`.
