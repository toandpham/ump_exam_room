"use strict";
// AD-103: bộ đo nghẽn tiến trình chính — chẩn đoán lag gõ phím trên máy yếu.
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const { createPerf, stallOf, keygapOf, TICK_MS, STALL_MS } = require("../src/perf");

test("stallOf: chỉ báo khi trễ vượt ngưỡng", () => {
  assert.equal(stallOf(TICK_MS), 0);                    // đúng nhịp → không ghi
  assert.equal(stallOf(TICK_MS + STALL_MS - 1), 0);     // dưới ngưỡng → bỏ qua
  assert.equal(stallOf(TICK_MS + 2000), 2000);          // kẹt 2s → ghi 2000
});

test("keygapOf: lọc gõ nhanh và nghỉ tay, giữ khoảng đáng ngờ", () => {
  assert.equal(keygapOf(200), 0);       // gõ bình thường
  assert.equal(keygapOf(2500), 2500);   // ~2.5s/phím = triệu chứng lag thật
  assert.equal(keygapOf(15000), 0);     // nghỉ tay đọc đề — không phải lag
});

test("createPerf: ghi start + keygap vào file, không nổ khi fs lỗi", () => {
  const file = "/tmp/perf-test-" + process.pid + ".log";
  try { fs.unlinkSync(file); } catch { /* ignore */ }
  let t = 1_000_000;
  const p = createPerf({ file, now: () => t });
  p.start("v9.9.9 keyblocker=on gpu=on");
  p.key();            // phím đầu — chưa có gap
  t += 2500; p.key(); // gap 2.5s → ghi
  t += 200;  p.key(); // gõ nhanh → không ghi
  p.stop();
  const lines = fs.readFileSync(file, "utf8").trim().split("\n");
  assert.equal(lines.length, 2);
  assert.match(lines[0], /start v9\.9\.9 keyblocker=on gpu=on/);
  assert.match(lines[1], /keygap 2500ms/);
  fs.unlinkSync(file);

  // fs hỏng → không throw (đo đạc không được phá app).
  const bad = createPerf({
    file: "/x",
    fsMod: { appendFileSync() { throw new Error("boom"); }, existsSync() { return false; }, statSync() { return { size: 0 }; }, unlinkSync() {} },
    now: () => 1,
  });
  assert.doesNotThrow(() => { bad.start("x"); bad.key(); bad.key(); bad.stop(); });
});

test("config: disableKeyblocker mặc định false, chỉ true khi khai đúng boolean", () => {
  const { loadConfig } = require("../src/config");
  assert.strictEqual(loadConfig("/khong-co-file").disableKeyblocker, false);
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ disableKeyblocker: true })).disableKeyblocker, true);
  assert.strictEqual(loadConfig("x", () => JSON.stringify({ disableKeyblocker: "true" })).disableKeyblocker, false);
});

test("main.js: keyblocker có công tắc + perf được nối", () => {
  const src = fs.readFileSync(require.resolve("../src/main.js"), "utf8");
  // Chỉ chạy keyblocker khi KHÔNG disable (A/B chẩn đoán).
  assert.match(src, /if \(cfg\.disableKeyblocker\)[\s\S]{0,200}else startKeyBlocker\(\)/);
  // Đo phím trong before-input-event + start perf với header rõ ràng.
  assert.match(src, /perf && input\.type === "keyDown"\) perf\.key\(\)/);
  assert.match(src, /perf\.start\(`v\$\{app\.getVersion\(\)\}/);
});
