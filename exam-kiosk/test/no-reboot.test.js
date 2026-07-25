"use strict";
// AD-93: thoát kiosk KHÔNG được khởi động lại máy, và PHẢI gỡ policy khoá máy.
// Đây là ràng buộc vận hành (phòng đang thi mà máy restart là hỏng cả buổi).
//
// Refactor đợt 3: 3 khối dọn dẹp trùng nhau (quitKiosk/quitForUpdate/will-quit)
// gộp thành teardown(). Test cũ grep `setTaskMgr(false)` NGAY TRONG quitKiosk nên
// vỡ khi code dời chỗ dù hành vi đúng → nay kiểm theo CHUỖI GỌI: quitKiosk phải
// gọi teardown(), và teardown phải gỡ policy + không có lệnh shutdown nào.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const src = fs.readFileSync(path.join(__dirname, "..", "src", "main.js"), "utf8");

/** Lấy thân một hàm khai báo kiểu `function ten() { ... }` (đếm ngoặc). */
function bodyOf(name) {
  const start = src.indexOf(`function ${name}(`);
  assert.notStrictEqual(start, -1, `không tìm thấy hàm ${name}`);
  let depth = 0, i = src.indexOf("{", start);
  for (let j = i; j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}" && --depth === 0) return src.slice(i, j + 1);
  }
  throw new Error(`không đóng ngoặc: ${name}`);
}

test("không chạy lệnh shutdown/restart của Windows", () => {
  // Bắt mọi kiểu gọi: execFile("shutdown"...), spawn("shutdown"...), exec("shutdown /r")
  const calls = src.match(/(execFile|execFileSync|spawn|exec)\s*\(\s*["'`]shutdown/gi);
  assert.strictEqual(calls, null, `còn lệnh shutdown trong main.js: ${calls}`);
  assert.ok(!/\/r["'`,\s]/.test(src.replace(/^\s*\/\/.*$/gm, "")),
    "còn tham số /r (restart) ngoài phần chú thích");
});

test("teardown() gỡ policy khoá + dừng bộ chặn phím (máy không kẹt Task Manager)", () => {
  const body = bodyOf("teardown");
  assert.match(body, /setTaskMgr\(false\)/);
  assert.match(body, /markLockdown\(false\)/);
  assert.match(body, /stopKeyBlocker\(\)/);
  assert.ok(!/shutdown/i.test(body), "teardown không được đụng lệnh shutdown");
});

test("mọi đường thoát đều đi qua teardown() rồi mới app.quit()", () => {
  for (const fn of ["quitKiosk", "quitForUpdate"]) {
    const body = bodyOf(fn);
    assert.match(body, /teardown\(\)/, `${fn} phải gọi teardown()`);
    assert.match(body, /app\.quit\(\)/, `${fn} phải gọi app.quit()`);
  }
  // will-quit (đường thoát do Electron khởi xướng) cũng phải dọn.
  const willQuit = src.slice(src.indexOf('app.on("will-quit"'), src.indexOf('app.on("window-all-closed"'));
  assert.match(willQuit, /teardown\(\)/);
});
