"use strict";
// Chính sách khoá máy (registry) — tách khỏi main.js ở refactor đợt 3 nên bộ lệnh
// test được thật, không cần chạm registry Windows.
const { test } = require("node:test");
const assert = require("node:assert");
const { policyCommands, POLICY_SUBKEYS } = require("../src/win-policy");

test("khoá máy: ADD mọi policy ở CẢ HKLM lẫn HKCU (elevated bằng tài khoản khác vẫn dính)", () => {
  const cmds = policyCommands(true);
  const keys = cmds.map((c) => c[1]);
  assert.ok(keys.some((k) => k.startsWith("HKLM\\Software")), "phải có HKLM");
  assert.ok(keys.some((k) => k.startsWith("HKCU\\Software")), "phải có HKCU");
  // 6 policy × 2 hive + shutdownwithoutlogon + HideFastUserSwitching
  assert.strictEqual(cmds.length, POLICY_SUBKEYS.length * 2 + 2);
  assert.ok(cmds.filter((c) => c[0] === "add").length === cmds.length, "khoá thì toàn ADD");
});

test("gỡ khoá: DELETE các policy + TRẢ LẠI nút nguồn (shutdownwithoutlogon=1)", () => {
  const cmds = policyCommands(false);
  const dels = cmds.filter((c) => c[0] === "delete");
  assert.strictEqual(dels.length, POLICY_SUBKEYS.length * 2 + 1);  // +1: HideFastUserSwitching
  const sd = cmds.find((c) => c.includes("shutdownwithoutlogon"));
  assert.strictEqual(sd[0], "add");
  assert.strictEqual(sd[sd.indexOf("/d") + 1], "1", "1 = hiện lại nút nguồn");
});

test("khoá máy tắt Task Manager + chặn Đăng xuất/Tắt máy từ Start", () => {
  const names = POLICY_SUBKEYS.map(([, n]) => n);
  for (const n of ["DisableTaskMgr", "DisableLockWorkstation", "NoLogoff", "NoClose"]) {
    assert.ok(names.includes(n), `thiếu policy ${n}`);
  }
});
