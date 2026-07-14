"use strict";
// Poll lệnh điều khiển từ server (quit = thoát máy; wipe = xoá đề + reload đăng nhập). KHÔNG import electron.
const http = require("http");

function fetchCommand(baseUrl) {
  return new Promise((resolve) => {
    const req = http.get(baseUrl + "/api/exam/kiosk/command", { timeout: 4000 }, (res) => {
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

module.exports = { fetchCommand, pollOnce, startPolling };
