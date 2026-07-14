"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { checkEmergencyPassword, handleEmergencyVerify } = require("../src/quit");

test("emergency password match", () => {
  assert.strictEqual(checkEmergencyPassword("ump@2026", "ump@2026"), true);
  assert.strictEqual(checkEmergencyPassword("wrong", "ump@2026"), false);
  assert.strictEqual(checkEmergencyPassword("", "ump@2026"), false);
  assert.strictEqual(checkEmergencyPassword(null, "ump@2026"), false);
});

test("handleEmergencyVerify fires onSuccess only on correct password", () => {
  let quits = 0;
  const onOk = () => { quits += 1; };
  assert.strictEqual(handleEmergencyVerify("ump@2026", "ump@2026", onOk), true);
  assert.strictEqual(quits, 1);
  assert.strictEqual(handleEmergencyVerify("nope", "ump@2026", onOk), false);
  assert.strictEqual(quits, 1);           // không gọi onSuccess khi sai
  assert.strictEqual(handleEmergencyVerify("", "ump@2026", onOk), false);
  assert.strictEqual(quits, 1);
});
