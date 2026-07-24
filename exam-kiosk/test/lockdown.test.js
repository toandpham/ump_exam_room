"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { isBlockedKey, keepOnTopActions, KIOSK_WINDOW_OPTS } = require("../src/lockdown");

const ev = (over) => ({ type: "keyDown", key: "", control: false, alt: false, shift: false, meta: false, ...over });

test("blocks escape keys", () => {
  assert.ok(isBlockedKey(ev({ key: "F11" })));
  assert.ok(isBlockedKey(ev({ key: "F12" })));
  assert.ok(isBlockedKey(ev({ key: "F5" })));                   // F5 tải lại trang
  assert.ok(isBlockedKey(ev({ key: "Tab", alt: true })));      // Alt+Tab
  assert.ok(isBlockedKey(ev({ key: "F4", alt: true })));        // Alt+F4
  assert.ok(isBlockedKey(ev({ key: "r", meta: true })));        // Win+R (any meta)
  assert.ok(isBlockedKey(ev({ key: "I", control: true, shift: true }))); // devtools
  assert.ok(isBlockedKey(ev({ key: "t", control: true })));     // Ctrl+T new tab
  assert.ok(isBlockedKey(ev({ key: "w", control: true })));     // Ctrl+W close
});

test("blocks all function keys + escape + window/system combos", () => {
  for (let i = 1; i <= 12; i++) assert.ok(isBlockedKey(ev({ key: "F" + i })), "F" + i);
  assert.ok(isBlockedKey(ev({ key: "Escape" })));               // Escape
  assert.ok(isBlockedKey(ev({ key: "Escape", alt: true })));    // Alt+Esc
  assert.ok(isBlockedKey(ev({ key: "Escape", control: true }))); // Ctrl+Esc (Start)
  assert.ok(isBlockedKey(ev({ key: " ", alt: true })));         // Alt+Space (system menu)
  assert.ok(isBlockedKey(ev({ key: "Tab", shift: true, alt: true }))); // Alt+Shift+Tab
  assert.ok(isBlockedKey(ev({ key: "d", meta: true })));        // Win+D
  assert.ok(isBlockedKey(ev({ key: "PrintScreen" })));
  assert.ok(isBlockedKey(ev({ key: "T", control: true, shift: true }))); // Ctrl+Shift+T reopen tab
  assert.ok(isBlockedKey(ev({ key: "p", control: true })));     // Ctrl+P print
});

test("allows normal typing + emergency combo + backspace + plain Tab", () => {
  assert.ok(!isBlockedKey(ev({ key: "a" })));
  assert.ok(!isBlockedKey(ev({ key: "5" })));
  assert.ok(!isBlockedKey(ev({ key: "Backspace" })));          // editing CCCD field
  assert.ok(!isBlockedKey(ev({ key: "Tab" })));                // plain Tab = chuyển ô nhập, cho phép
  assert.ok(!isBlockedKey(ev({ key: "Q", control: true, alt: true, shift: true }))); // escape hatch
  assert.ok(!isBlockedKey(ev({ key: "F12", type: "keyUp" }))); // keyUp ignored
});

test("keepOnTop: no-op khi trạng thái đã đúng (đang gõ → không chặn tiến trình chính)", () => {
  // Trạng thái bình thường lúc thí sinh gõ: đang trên-cùng + kiosk + focus, không minimize.
  const a = keepOnTopActions({ alwaysOnTop: true, kiosk: true, minimized: false, focused: true });
  assert.strictEqual(a.setAlwaysOnTop, false);
  assert.strictEqual(a.setKiosk, false);
  assert.strictEqual(a.restore, false);
  assert.strictEqual(a.refocus, false);
});

test("keepOnTop: giành lại khi z-order/focus bị đổi (vd sau Ctrl+Alt+Del)", () => {
  const a = keepOnTopActions({ alwaysOnTop: false, kiosk: false, minimized: true, focused: false });
  assert.strictEqual(a.setAlwaysOnTop, true);
  assert.strictEqual(a.setKiosk, true);
  assert.strictEqual(a.restore, true);
  assert.strictEqual(a.refocus, true);
  // Chỉ mất focus (đang trên-cùng + kiosk) → chỉ refocus, không đụng always-on-top/kiosk.
  const b = keepOnTopActions({ alwaysOnTop: true, kiosk: true, minimized: false, focused: false });
  assert.deepStrictEqual(b, { setAlwaysOnTop: false, setKiosk: false, restore: false, refocus: true });
});

test("window opts are kiosk + locked", () => {
  assert.strictEqual(KIOSK_WINDOW_OPTS.kiosk, true);
  assert.strictEqual(KIOSK_WINDOW_OPTS.alwaysOnTop, true);
  assert.strictEqual(KIOSK_WINDOW_OPTS.webPreferences.nodeIntegration, false);
  assert.strictEqual(KIOSK_WINDOW_OPTS.webPreferences.contextIsolation, true);
  assert.strictEqual(KIOSK_WINDOW_OPTS.webPreferences.devTools, false);   // chặn DevTools
  assert.strictEqual(KIOSK_WINDOW_OPTS.webPreferences.sandbox, true);     // sandbox renderer
});
