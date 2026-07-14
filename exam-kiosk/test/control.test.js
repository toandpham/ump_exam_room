"use strict";
const { test, mock } = require("node:test");
const assert = require("node:assert");
const http = require("node:http");
const { pollOnce, fetchCommand, startPolling } = require("../src/control");

const delay = (ms) => new Promise((r) => setTimeout(r, ms));

test("pollOnce returns {quit, wipe} fields", async () => {
  assert.deepStrictEqual(await pollOnce(async () => ({ quit: true })),          { quit: true,  wipe: false });
  assert.deepStrictEqual(await pollOnce(async () => ({ quit: false })),         { quit: false, wipe: false });
  assert.deepStrictEqual(await pollOnce(async () => ({ quit: false, wipe: true })), { quit: false, wipe: true });
  assert.deepStrictEqual(await pollOnce(async () => ({})),                      { quit: false, wipe: false });
  assert.deepStrictEqual(await pollOnce(async () => null),                      { quit: false, wipe: false });
});

test("fetchCommand returns {quit:true,wipe:false} from a server", async () => {
  const server = http.createServer((_req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ quit: true }));
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const baseUrl = "http://127.0.0.1:" + server.address().port;
  assert.deepStrictEqual(await fetchCommand(baseUrl), { quit: true, wipe: false });
  await new Promise((r) => server.close(r));
});

test("fetchCommand returns {quit:false,wipe:false} on connection error", async () => {
  // Cổng 1 không có gì lắng nghe — phải trả về {quit:false,wipe:false}, không ném lỗi.
  assert.deepStrictEqual(await fetchCommand("http://127.0.0.1:1"), { quit: false, wipe: false });
});

test("startPolling fires onQuit when getter returns quit", async () => {
  let quitCalled = false;
  let resolveQuit;
  const quitPromise = new Promise((r) => { resolveQuit = r; });
  const stop = startPolling({
    getter: async () => ({ quit: true }),
    intervalMs: 10,
    onQuit: () => { quitCalled = true; resolveQuit(); },
  });
  await quitPromise;
  stop();
  assert.ok(quitCalled);
});

test("startPolling fires onWipe once per flag cycle, not every tick", async () => {
  let wipeFlag = true;
  const onWipe = mock.fn();
  const onQuit = mock.fn();
  const stop = startPolling({
    getter: async () => ({ quit: false, wipe: wipeFlag }),
    intervalMs: 5, onQuit, onWipe,
  });
  await delay(40);                   // vài tick — chỉ 1 lần wipe
  assert.strictEqual(onWipe.mock.callCount(), 1);
  wipeFlag = false; await delay(20); // cờ tắt → reset guard
  wipeFlag = true;  await delay(20); // bật lại → wipe lần 2
  assert.strictEqual(onWipe.mock.callCount(), 2);
  assert.strictEqual(onQuit.mock.callCount(), 0);
  stop();
});

test("startPolling fires onWipe again after flag goes false then true", async () => {
  let wipeFlag = false;
  const onWipe = mock.fn();
  const stop = startPolling({
    getter: async () => ({ quit: false, wipe: wipeFlag }),
    intervalMs: 5, onQuit: mock.fn(), onWipe,
  });
  await delay(20);                   // cờ false — chưa wipe
  assert.strictEqual(onWipe.mock.callCount(), 0);
  wipeFlag = true;  await delay(20); // bật → wipe lần 1
  assert.strictEqual(onWipe.mock.callCount(), 1);
  wipeFlag = false; await delay(20); // tắt → reset guard
  wipeFlag = true;  await delay(20); // bật lại → wipe lần 2
  assert.strictEqual(onWipe.mock.callCount(), 2);
  stop();
});

test("quit takes precedence over wipe and stops polling", async () => {
  const onWipe = mock.fn();
  const onQuit = mock.fn();
  let resolveQuit;
  const quitPromise = new Promise((r) => { resolveQuit = r; });
  const stop = startPolling({
    getter: async () => ({ quit: true, wipe: true }),
    intervalMs: 5,
    onQuit: () => { onQuit(); resolveQuit(); },
    onWipe,
  });
  await quitPromise;
  await delay(20);                   // thêm thời gian để đảm bảo không có thêm call
  assert.strictEqual(onQuit.mock.callCount(), 1);  // dừng sau lần đầu
  assert.strictEqual(onWipe.mock.callCount(), 0);  // quit ưu tiên, không gọi wipe
  stop();
});
