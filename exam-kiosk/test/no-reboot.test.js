"use strict";
// AD-93: thoát kiosk KHÔNG được khởi động lại máy. Đây là ràng buộc vận hành
// (phòng đang thi mà máy restart là hỏng cả buổi), nên khoá lại bằng test đọc
// thẳng mã nguồn: không được có lệnh gọi `shutdown` nào nữa.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const src = fs.readFileSync(path.join(__dirname, "..", "src", "main.js"), "utf8");

test("không chạy lệnh shutdown/restart của Windows", () => {
  // Bắt mọi kiểu gọi: execFile("shutdown"...), spawn("shutdown"...), exec("shutdown /r")
  const calls = src.match(/(execFile|execFileSync|spawn|exec)\s*\(\s*["'`]shutdown/gi);
  assert.strictEqual(calls, null, `còn lệnh shutdown trong main.js: ${calls}`);
  assert.ok(!/\/r["'`,\s]/.test(src.replace(/^\s*\/\/.*$/gm, "")),
    "còn tham số /r (restart) ngoài phần chú thích");
});

test("vẫn gỡ policy khoá khi thoát (máy không bị kẹt Task Manager)", () => {
  const quit = src.slice(src.indexOf("function quitKiosk()"));
  assert.match(quit.slice(0, 600), /setTaskMgr\(false\)/);
  assert.match(quit.slice(0, 600), /markLockdown\(false\)/);
  assert.match(quit.slice(0, 600), /app\.quit\(\)/);
});
