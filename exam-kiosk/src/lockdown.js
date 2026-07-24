"use strict";
// Quyết định chặn phím (thuần, test được) + options cửa sổ kiosk.
// KHÔNG import electron ở top-level.

// Phím đơn bị chặn: mọi phím chức năng F1..F12, PrintScreen, Escape.
const FN_KEYS = Array.from({ length: 12 }, (_, i) => "F" + (i + 1));
const BLOCKED_SINGLE = new Set([...FN_KEYS, "PrintScreen", "Escape"]);
const DEVTOOLS = new Set(["I", "J", "C", "K"]);             // với Ctrl+Shift
// Ctrl + <phím>: reload/đóng-mở tab, in, lưu, mở file, view-source, zoom…
// AD-76: bỏ "A" — Ctrl+A (chọn tất cả) là thao tác hợp lệ trong ô Giấy nháp /
// ô nhập CCCD (cùng bài học "máy tính nuốt phím" AD-69). Không có nguy cơ thoát.
const CTRL_BLOCK = new Set(["R", "W", "T", "N", "P", "S", "O", "U", "+", "-", "=", "0", "F", "G", "H", "J", "D"]);
// Ctrl + Shift + <phím>: mở lại tab/cửa sổ ẩn danh, downloads…
const CTRL_SHIFT_BLOCK = new Set(["T", "N", "W", "Q", "J", "DELETE"]);

function isBlockedKey(input) {
  if (!input || input.type === "keyUp") return false;
  const key = input.key || "";
  const upper = key.toUpperCase();
  const ctrl = !!input.control, alt = !!input.alt, shift = !!input.shift, meta = !!input.meta;

  // Lối thoát khẩn cấp Ctrl+Alt+Shift+Q phải LỌT qua (xử lý riêng ở main.js).
  if (ctrl && alt && shift && upper === "Q") return false;

  if (meta) return true;                                     // mọi tổ hợp phím Windows (Win)
  if (BLOCKED_SINGLE.has(key)) return true;                  // F1..F12, PrintScreen, Escape
  // Alt + Tab/Esc/F4/Space (mở System menu)/mũi tên: chuyển/đóng cửa sổ.
  if (alt && (key === "Tab" || key === "Escape" || key === "F4" || key === " " || key === "Spacebar" || key.startsWith("Arrow"))) return true;
  if (ctrl && key === "Escape") return true;                 // Ctrl+Esc = mở Start menu
  if (ctrl && shift && (DEVTOOLS.has(upper) || CTRL_SHIFT_BLOCK.has(upper))) return true;
  if (ctrl && !shift && !alt && CTRL_BLOCK.has(upper)) return true;
  return false;
}

// Quyết định "giữ cửa sổ trên cùng" cần làm GÌ, dựa trên trạng thái HIỆN TẠI của
// cửa sổ. Trả về các cờ hành động — chỉ gọi API Windows tương ứng khi cờ = true.
// LÝ DO (fix giật gõ phím trên máy yếu): trước đây vòng lặp 600ms gọi
// setKiosk()/setAlwaysOnTop() VÔ ĐIỀU KIỆN; mỗi lần gọi chặn tiến trình chính
// ~1s trên máy cũ, mà mọi phím phải qua tiến trình chính (before-input-event) →
// gõ 1 ký tự chờ 1-2s. Khi trạng thái ĐÃ đúng (đang trên-cùng + kiosk + focus),
// mọi cờ = false → vòng lặp KHÔNG gọi API nào → tiến trình chính rảnh → phím tới
// tức thì. Không giảm khoá máy: khi z-order thực sự đổi (Ctrl+Alt+Del…), trạng
// thái sai → cờ bật lại + sự kiện blur/minimize kéo lại ngay.
function keepOnTopActions(state) {
  const s = state || {};
  return {
    setAlwaysOnTop: !s.alwaysOnTop,
    setKiosk: !s.kiosk,
    restore: !!s.minimized,
    refocus: !s.focused,
  };
}

const KIOSK_WINDOW_OPTS = {
  kiosk: true,
  fullscreen: true,
  frame: false,
  alwaysOnTop: true,
  autoHideMenuBar: true,
  webPreferences: {
    contextIsolation: true,
    nodeIntegration: false,
    devTools: false,   // chặn mở DevTools kể cả khi qua được phím tắt
    // LƯU Ý TRUNG THỰC (AD-76): main.js đang bật switch --no-sandbox TOÀN CỤC
    // (bắt buộc — AV trên máy Win10 thật giết tiến trình Chromium sandboxed,
    // crash 0x80000003). Cờ sandbox:true dưới đây vì thế KHÔNG có tác dụng chừng
    // nào switch còn đó; giữ lại để nếu ngày nào gỡ được --no-sandbox thì từng
    // renderer tự về đúng trạng thái an toàn. Bù đắp: contextIsolation +
    // nodeIntegration:false + guard điều hướng same-origin + IPC chỉ nhận từ splash.
    sandbox: true,
    // preload gán ở main.js (đường dẫn tuyệt đối).
  },
};

module.exports = { isBlockedKey, keepOnTopActions, KIOSK_WINDOW_OPTS };
