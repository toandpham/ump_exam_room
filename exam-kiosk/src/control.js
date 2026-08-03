"use strict";
// Poll lệnh điều khiển từ server (quit = thoát máy; wipe = xoá đề + reload đăng nhập). KHÔNG import electron.
const http = require("http");

// AD-128: khai máy mình (device_id của app thi, lấy từ localStorage) để nhận được
// lệnh thoát nhắm riêng máy này — giám thị đóng 1 máy hoặc cả phòng. Không biết máy
// (chưa ai đăng nhập) → gọi trơn như trước, vẫn nhận lệnh cấp cả kỳ thi.
function commandUrl(baseUrl, deviceId) {
  const base = baseUrl + "/api/exam/kiosk/command";
  return deviceId ? base + "?device=" + encodeURIComponent(deviceId) : base;
}

function fetchCommand(baseUrl, deviceId) {
  return new Promise((resolve) => {
    const req = http.get(commandUrl(baseUrl, deviceId), { timeout: 4000 }, (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        try {
          const j = JSON.parse(body);
          resolve({ quit: !!(j && j.quit), wipe: !!(j && j.wipe) });
        } catch (_e) {
          resolve({ quit: false, wipe: false });
        }
      });
    });
    req.on("error", () => resolve({ quit: false, wipe: false }));
    req.on("timeout", () => { req.destroy(); resolve({ quit: false, wipe: false }); });
  });
}

async function pollOnce(getter) {
  const cmd = await getter();
  return { quit: !!(cmd && cmd.quit), wipe: !!(cmd && cmd.wipe) };
}

function startPolling({ getter, intervalMs, onQuit, onWipe }) {
  let wiped = false;   // guard: chỉ wipe 1 lần/chu kỳ cờ (tránh reload-loop)
  const timer = setInterval(async () => {
    try {
      const cmd = await pollOnce(getter);
      if (cmd.quit) { clearInterval(timer); onQuit(); return; }
      if (cmd.wipe) {
        if (!wiped) { wiped = true; if (onWipe) onWipe(); }
      } else {
        wiped = false;   // cờ tắt → cho phép wipe lần sau
      }
    } catch (_e) { /* nuốt lỗi mạng — poll tiếp */ }
  }, intervalMs);
  return () => clearInterval(timer);
}

module.exports = { commandUrl, fetchCommand, pollOnce, startPolling };
