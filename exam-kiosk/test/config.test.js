"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { loadConfig, DEFAULTS } = require("../src/config");

test("missing/invalid file → all defaults", () => {
  assert.deepStrictEqual(loadConfig("/no/such/file.json"), DEFAULTS);
  const bad = () => "{ not json";
  assert.deepStrictEqual(loadConfig("x", bad), DEFAULTS);
});

test("overrides merge over defaults", () => {
  const reader = () => JSON.stringify({ emergencyPassword: "secret", controlPollMs: 3000 });
  const cfg = loadConfig("x", reader);
  assert.strictEqual(cfg.emergencyPassword, "secret");
  assert.strictEqual(cfg.controlPollMs, 3000);
  assert.strictEqual(cfg.serverHost, "exam-server"); // default kept
});

// AD-76: typo trong config không được phá vận hành — poll quá nhanh (50ms) từng
// là kiểu tải dập server ở sự cố 29-06; password không phải string thì không bao
// giờ thoát khẩn cấp được.
test("validate: controlPollMs clamp về [2000..60000], sai kiểu → default", () => {
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ controlPollMs: 50 })).controlPollMs, 2000);
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ controlPollMs: 999999 })).controlPollMs, 60000);
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ controlPollMs: "5000" })).controlPollMs, 5000);
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ controlPollMs: "abc" })).controlPollMs, DEFAULTS.controlPollMs);
});

test("validate: emergencyPassword luôn là string, host/path không rỗng", () => {
  const cfg = loadConfig("x", () => JSON.stringify({ emergencyPassword: 123456, serverHost: "", path: null }));
  assert.strictEqual(cfg.emergencyPassword, "123456");
  assert.strictEqual(cfg.serverHost, DEFAULTS.serverHost);
  assert.strictEqual(cfg.path, DEFAULTS.path);
});

test("serverIp: mặc định rỗng; nhận IP tĩnh + tự trim", () => {
  assert.strictEqual(DEFAULTS.serverIp, "");
  assert.strictEqual(loadConfig("/no/file").serverIp, "");
  assert.strictEqual(
    loadConfig("x", () => JSON.stringify({ serverIp: " 192.168.1.10 " })).serverIp,
    "192.168.1.10");
});
