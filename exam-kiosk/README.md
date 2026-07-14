# Exam Kiosk (Electron) — trình duyệt thi cho Windows 7

Trình duyệt thi tối giản thay SEB (AD-66). Cắm máy thi vào LAN → mở app → **tự tìm
máy chủ thi qua mDNS** → vào thẳng trang thí sinh ở chế độ kiosk khoá phím.

## Vì sao chạy được trên Win7
Electron 22 (Chromium 108) là bản Electron cuối còn hỗ trợ Windows 7. App tự phân
giải mDNS (Win7 không có Bonjour nên OS không tự làm được) → tìm được server dù
không có IP tĩnh / không có IT.

## ⚠️ Mức bảo mật
KHÔNG mạnh bằng SEB. Chặn được phần lớn (Alt+Tab, phím Windows, Alt+F4, F11/F12,
tab/cửa sổ mới, devtools…), NHƯNG **Ctrl+Alt+Del** là ranh giới Windows — app
user-mode không chặn tuyệt đối. ⇒ **Vẫn cần giám thị coi thi.**

## Thoát app
- **Thường:** chủ tịch bấm "Thoát tất cả máy thi" trên trang quản trị → các máy tự
  đóng trong ~5s.
- **Khẩn cấp (khi server/mạng hỏng):** Ctrl+Alt+Shift+Q → hiện **cửa sổ nhập mật khẩu
  riêng do app tạo** (không phụ thuộc trang đang mở, nên vẫn thoát được kể cả khi đã vào
  trang thi và mất kết nối server) → mật khẩu (mặc định `ump@2026`, ĐỔI trước production).

## Tự hồi phục khi mất kết nối / crash
- **Mất mạng sau khi đã vào trang thi:** app tự thử nạp lại trang theo backoff
  (2s, 4s, 6s… tối đa 10s). Sau 5 lần thất bại liên tiếp → quay về màn splash / nhập IP
  thủ công (không kẹt ở trang lỗi của Chromium).
- **Crash/bị kill giữa chừng:** app ghi 1 file "sentinel" trong `userData` khi đã áp
  lockdown registry (tắt Task Manager / khoá máy / nút nguồn…). Nếu lần chạy trước crash
  để sót lockdown, lần khởi động sau phát hiện sentinel → **tự khôi phục registry** trước
  khi áp lại. Nhờ vậy máy không bị kẹt với Task Manager bị tắt sau một lần app chết.

## Kiosk tìm server ở đâu?
Thứ tự: **IP đã nhớ (lần trước) → IP cấu hình sẵn (`serverIp`) → mDNS `exam-server.local`
→ nhập IP tay**. Có 3 cách để kiosk ra được server:

1. **mDNS (zero-config)** — server tự quảng bá `exam-server.local`:
   - **Mac:** `scutil --set LocalHostName exam-server`
   - **Linux (server nhà trường):** `install.sh` tự cài + cấu hình **Avahi** quảng bá
     `exam-server.local` (không đổi hostname máy). Cần LAN cho phép multicast/mDNS.
2. **IP tĩnh trong config (chắc ăn nhất — không phụ thuộc mDNS)** — đặt `serverIp` trong
   `kiosk.config.json`. Dùng khi switch trường chặn multicast, hoặc muốn cố định.
3. **Nhập IP tay** — lưới cuối, giám thị gõ IP server rồi kiosk nhớ lại.

(Server vẫn để `SEB_ENFORCE=false`.)

## Cấu hình (tuỳ chọn)
Tạo `kiosk.config.json` đặt cạnh file cài để đè mặc định (xem `kiosk.config.example.json`):
```json
{
  "serverIp": "192.168.1.10",
  "serverHost": "exam-server",
  "emergencyPassword": "ĐỔI_TÔI",
  "controlPollMs": 5000
}
```
- `serverIp`: IP (hoặc `host:port`) TĨNH của server thi — đặt cái này thì kiosk kết nối
  **thẳng, không cần mDNS**. Để trống `""` → chỉ dùng mDNS.
- Không có file → dùng mặc định (chỉ mDNS `exam-server.local`).

## native/keyblocker.exe (BẮT BUỘC cho khoá máy)
`resources/keyblocker.exe` là artifact **prebuilt, đã .gitignore** (không có trong repo).
Đây là low-level keyboard hook chặn các tổ hợp hệ thống mà Electron user-mode KHÔNG nuốt
được (phím Windows, Alt+Tab, Alt+Esc, Ctrl+Esc, phím menu). **Thiếu file này → app vẫn
chạy nhưng phần khoá phím cốt lõi TẮT** (app in cảnh báo TO ra console lúc khởi động).

Build (cross-compile trên Mac bằng mingw, lệnh cũng ghi trong `native/keyblocker.c`):
```
brew install mingw-w64
i686-w64-mingw32-gcc native/keyblocker.c -o resources/keyblocker.exe -mwindows -O2 -s
```

## Tự cập nhật qua server (AD-84)
Máy thi tự cập nhật kiosk từ server — không phải đi copy `.exe` từng máy khi có bản vá.

**Cơ chế:** server phát `http://<server>/kiosk/` = `latest.json` + `latest.json.sig` + file
`.exe` (thư mục `kiosk-release/`, Caddy phục vụ, KHÔNG dính license). Kiosk **lúc khởi động,
TRƯỚC khi thí sinh vào đề** (an toàn) đọc `latest.json`; nếu `version` mới hơn → hiện màn
"Đang cập nhật phần mềm thi…", tải `.exe`, cài im lặng (`/S`), khởi động lại. **Fail-safe
tuyệt đối:** mọi lỗi (mạng, tải, cài) → bỏ qua, vào đề bằng bản hiện tại. Không cập nhật GIỮA bài.

**Bảo mật (AD-85):** cài im lặng file .exe với quyền admin là bề mặt tấn công lớn → kiosk
**KHÔNG tin transport (HTTP)**, mà tin **chữ ký**: `latest.json` được **ký Ed25519 bằng khoá
bí mật offline** của nhà cung cấp (cùng cặp khoá với license, `~/.exam-license`); kiosk verify
bằng **khoá công khai nhúng sẵn** trước khi tin `version/file`, rồi kiểm **SHA-256** file .exe
khớp manifest đã ký. Kẻ trong LAN giả mDNS/đổi IP/tráo .exe đều KHÔNG ký được → kiosk từ chối.
`file` còn bị ràng regex `^[A-Za-z0-9._-]+\.exe$` (chặn path traversal). Vì thế HTTP offline
(AD-18/64) là chấp nhận được — an toàn đến từ chữ ký, không phải TLS.

**Quy trình phát hành 1 bản mới:**
1. Sửa code kiosk + **bump `version`** trong `package.json` (bắt buộc — kiosk so version).
2. `./release.sh` → build `.exe` + cập nhật `../kiosk-release/` (`.exe` + `latest.json`).
3. `git add -A && git commit -m "release kiosk vX.Y.Z" && git push`.
4. Trên **server thi**: `./update.sh` (kéo bản mới → server phát).
5. Máy thi lần khởi động kế **tự cập nhật**.

**Lưu ý:**
- Thứ tự tìm bản: chỉ so version số (`1.10.0 > 1.9.0`). Config `serverIp`/mDNS quyết định
  server nào phát.
- Bản kiosk ĐANG cài trên máy phải là **≥ v1.2.0** (bản đầu có auto-update) — bản cũ hơn
  phải cài tay 1 lần lên 1.2.0, từ đó về sau tự cập nhật.
- ⚠️ **Cài im lặng + tự khởi động lại trên Windows CHƯA test được ở máy dev (không có Win)**
  — phải nghiệm thu trên 1 máy Windows thật trước khi tin dùng. Nếu installer không tự chạy
  lại app sau khi cài `/S`, cần bật autostart (Task Scheduler onlogon, xem mục vận hành).
- 400 máy cùng tải ~62MB lúc boot = tải dồn; rải theo giờ boot, LAN dây thì ổn.

## Build .exe
Một target duy nhất (AD-76, bỏ bản portable): **NSIS installer** ia32 — chạy trên mọi
Windows 7→11, cả 32 lẫn 64-bit.

```
npm install     # lần đầu
npm run dist    # → dist/UMP_ExamKiosk-Setup.exe   (NSIS installer, ia32)
```

- **Installer** (`UMP_ExamKiosk-Setup.exe`): NSIS, `perMachine` + `requestedExecutionLevel:
  requireAdministrator` → cài bằng quyền admin nên các chính sách Ctrl+Alt+Del cấp MÁY (HKLM:
  ẩn nút nguồn / Switch user) áp được tự động; tạo shortcut Desktop + Start Menu "UMP ExamKiosk".
  (KHÔNG phát bản portable: chạy từ thư mục ghi-được, thí sinh sửa `kiosk.config.json`
  đổi mật khẩu thoát được — bản cài vào Program Files thì ACL chặn.)
- **Build ngay trên Mac được** — KHÔNG cần wine (electron-builder đóng gói nsis native;
  đã verify ra `arch=ia32`). Build trên Windows cũng cho kết quả tương đương.
- Script đã ép `--ia32` (đừng để electron-builder lấy arch của máy host — Mac Apple Silicon
  sẽ ra arm64 vô dụng). `npm run dist:dir` (thêm `--ia32`) tạo thư mục unpacked nếu cần.
- File ra ~58MB (Chromium đi kèm) — copy qua LAN/USB sang từng máy thi.

## Chạy thử (dev)
`npm start` (cần `docker compose up -d` để server trả `/api/health`).

## Test
`npm test` (node:test — config / discovery / control / lockdown / quit).

## Tự chạy khi bật máy (tuỳ chọn)
⚠️ KHÔNG dùng `shell:startup` — app đòi quyền admin (`requireAdministrator`) nên Windows
**chặn im lặng** app elevation trong Startup folder (máy boot xong không có kiosk, không
báo lỗi). Dùng **Task Scheduler** (chạy 1 lần bằng CMD quyền admin trên mỗi máy thi):

```
schtasks /create /tn "UMP_ExamKiosk" /sc onlogon /rl HIGHEST /f ^
  /tr "\"C:\Program Files\UMP_ExamKiosk\UMP_ExamKiosk.exe\""
```

Gỡ: `schtasks /delete /tn "UMP_ExamKiosk" /f`.

## Lưu ý vận hành
- **Sau lệnh "Xoá dữ liệu máy thi" (wipe)**: localStorage bị xoá → mã thiết bị sinh mới →
  lần đăng nhập kế backend coi là "thiết bị khác", màn giám sát có thể hiện loạt cảnh báo
  đổi thiết bị — bình thường, không phải sự cố.
- **Không dùng song song** app kiosk và file `IT/khoa-ctrl-alt-del.reg` (khoá tay): khi thoát,
  app khôi phục registry sẽ gỡ luôn chính sách IT đặt tay. Chọn MỘT trong hai.
- **Crash/cúp điện khi đang khoá**: nếu máy không chạy lại app (app tự lành khi chạy lại),
  dùng `restore-shutdown.bat` để gỡ khoá registry tay.
- **Mức bảo mật**: app chạy `--no-sandbox` (bắt buộc để sống chung AV trên máy Win10 thật);
  bù bằng contextIsolation + khoá điều hướng same-origin + IPC chỉ nhận từ splash. Vẫn cần
  giám thị coi thi — Ctrl+Alt+Del không chặn tuyệt đối được (ranh giới Windows).

## Firewall
Lần đầu Windows có thể hỏi "Allow access" (mDNS) → bấm Allow. Hoặc thêm rule sẵn:
```
netsh advfirewall firewall add rule name="UMP_ExamKiosk" dir=in action=allow program="C:\path\UMP_ExamKiosk.exe" enable=yes
```
