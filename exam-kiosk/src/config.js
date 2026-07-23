"use strict";
// Cấu hình kiosk: hard-code mặc định, cho phép đè bằng kiosk.config.json cạnh app.
// KHÔNG import electron ở đây (để test được dưới Node thường).
const fs = require("fs");

const DEFAULTS = {
  serverHost: "exam-server",       // tên mDNS để hỏi (→ exam-server.local)
  serverIp: "",                     // IP/host TĨNH server (vd "192.168.1.10") — đặt cho
                                    // server nhà trường không mDNS; "" = chỉ dùng mDNS
  path: "/thisinh/",                // trang thí sinh
  emergencyPassword: "ump@2026",    // mật khẩu thoát KHẨN CẤP (đổi trước production)
  discoveryTimeoutMs: 5000,         // timeout tìm server
  controlPollMs: 5000,              // nhịp poll lệnh thoát từ server
  disableGpu: false,                // AD-95: true = ép vẽ bằng CPU (SwiftShader).
                                    // Mặc định false = BẬT GPU (mượt hơn nhiều trên
                                    // máy yếu). Đặt true cho máy nào bật GPU bị lỗi
                                    // (app tự phát hiện + tự tắt nên hiếm khi cần).
};

function loadConfig(filePath, readFile = fs.readFileSync) {
  let overrides = {};
  try {
    const parsed = JSON.parse(readFile(filePath, "utf8"));
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) overrides = parsed;
  } catch (_e) {
    overrides = {}; // thiếu file / JSON hỏng → dùng toàn bộ mặc định
  }
  const cfg = { ...DEFAULTS, ...overrides };
  // AD-76: validate kiểu — typo trong kiosk.config.json không được phá vận hành.
  // controlPollMs=50 (thiếu số 0) → 400 máy × 20 req/s dập server (vết sự cố
  // 29-06); password không phải string → không bao giờ thoát khẩn cấp được.
  const poll = Number(cfg.controlPollMs);
  cfg.controlPollMs = Number.isFinite(poll) ? Math.min(Math.max(poll, 2000), 60000) : DEFAULTS.controlPollMs;
  const disc = Number(cfg.discoveryTimeoutMs);
  cfg.discoveryTimeoutMs = Number.isFinite(disc) ? Math.min(Math.max(disc, 1000), 30000) : DEFAULTS.discoveryTimeoutMs;
  cfg.emergencyPassword = String(cfg.emergencyPassword ?? DEFAULTS.emergencyPassword);
  cfg.serverHost = String(cfg.serverHost || DEFAULTS.serverHost);
  cfg.serverIp = String(cfg.serverIp ?? "").trim();   // "" = không đặt (chỉ mDNS)
  cfg.path = String(cfg.path || DEFAULTS.path);
  cfg.disableGpu = cfg.disableGpu === true;   // chỉ true khi khai đúng boolean true
  return cfg;
}

module.exports = { DEFAULTS, loadConfig };
