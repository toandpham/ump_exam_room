"use strict";
// AD-95: GPU bật mặc định để máy yếu đỡ giật; tự dò tự tắt cho máy driver lỗi.
// Refactor đợt 3: logic quyết định tách sang src/gpu.js nên test được THẬT
// (trước đây chỉ grep chuỗi trong main.js — vỡ ngay khi refactor dù hành vi đúng).
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { loadConfig } = require("../src/config");
const { decideGpu } = require("../src/gpu");

test("disableGpu mặc định false (BẬT GPU) và chỉ true khi khai đúng boolean", () => {
  assert.strictEqual(loadConfig("/khong-co-file").disableGpu, false);
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ disableGpu: true })).disableGpu, true);
  // Giá trị lạ (chuỗi, số) không được vô tình tắt GPU.
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ disableGpu: "true" })).disableGpu, false);
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ disableGpu: 1 })).disableGpu, false);
});

test("máy sạch (không cờ nào) → BẬT GPU + ghi cờ đang-thử", () => {
  const d = decideGpu({ configDisable: false, offFlag: false, probeFlag: false });
  assert.strictEqual(d.disable, false);
  assert.strictEqual(d.writeProbe, true);   // để lần sau biết lần này có hoàn tất không
  assert.strictEqual(d.markBad, false);
});

test("lần trước CHẾT khi đang thử GPU (còn cờ probe) → tắt GPU + đánh dấu vĩnh viễn", () => {
  const d = decideGpu({ configDisable: false, offFlag: false, probeFlag: true });
  assert.strictEqual(d.disable, true);
  assert.strictEqual(d.markBad, true);      // ghi gpu-off.flag cho các lần sau
  assert.match(d.reason, /crash/);
});

test("máy đã bị đánh dấu GPU hỏng → tắt GPU, KHÔNG ghi lại cờ thử", () => {
  const d = decideGpu({ configDisable: false, offFlag: true, probeFlag: false });
  assert.strictEqual(d.disable, true);
  assert.strictEqual(d.writeProbe, false);
  assert.strictEqual(d.markBad, false);
});

test("ép tắt bằng kiosk.config.json → tắt GPU, thắng mọi cờ khác", () => {
  const d = decideGpu({ configDisable: true, offFlag: false, probeFlag: true });
  assert.strictEqual(d.disable, true);
  assert.match(d.reason, /cấu hình/);
  assert.strictEqual(d.markBad, false);     // không đổ lỗi cho phần cứng
});

test("main.js dùng module gpu (không tự quyết định trong file)", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "src", "main.js"), "utf8");
  assert.match(src, /require\(["']\.\/gpu["']\)/);
  // Mọi lần tắt GPU vẫn phải đi qua đúng 1 chỗ.
  const calls = src.match(/app\.disableHardwareAcceleration\(\)/g) || [];
  assert.strictEqual(calls.length, 1, "chỉ được gọi 1 lần, bên trong disableGpuNow()");
});
