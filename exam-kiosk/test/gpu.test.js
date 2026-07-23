"use strict";
// AD-95: GPU bật mặc định để máy yếu đỡ giật; tự dò tự tắt cho máy driver lỗi.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { loadConfig } = require("../src/config");

test("disableGpu mặc định false (BẬT GPU) và chỉ true khi khai đúng boolean", () => {
  assert.strictEqual(loadConfig("/khong-co-file").disableGpu, false);
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ disableGpu: true })).disableGpu, true);
  // Giá trị lạ (chuỗi, số) không được vô tình tắt GPU.
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ disableGpu: "true" })).disableGpu, false);
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ disableGpu: 1 })).disableGpu, false);
});

test("main.js: GPU chỉ tắt CÓ ĐIỀU KIỆN (không còn tắt cứng vô điều kiện)", () => {
  const src = fs.readFileSync(path.join(__dirname, "..", "src", "main.js"), "utf8");
  // Không còn lời gọi disableHardwareAcceleration() ở cấp module (ngoài hàm).
  // Mọi lần tắt GPU phải đi qua disableGpuNow() có điều kiện.
  const calls = src.match(/app\.disableHardwareAcceleration\(\)/g) || [];
  assert.strictEqual(calls.length, 1, "chỉ được gọi 1 lần, bên trong disableGpuNow()");
  const fn = src.slice(src.indexOf("function disableGpuNow"), src.indexOf("function disableGpuNow") + 400);
  assert.match(fn, /app\.disableHardwareAcceleration\(\)/, "disableHardwareAcceleration phải nằm TRONG disableGpuNow");
  // Có 3 nhánh quyết định: config, cờ gpu-off, cờ probe leftover.
  assert.match(src, /cfg\.disableGpu/);
  assert.match(src, /gpuOffFile/);
  assert.match(src, /gpuProbeFile/);
  assert.match(src, /clearGpuProbe\(\)/);
});
