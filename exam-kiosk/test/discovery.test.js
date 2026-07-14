"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const { discoverServer } = require("../src/discovery");

test("cached IP used when healthy (skips mDNS)", async () => {
  let mdnsCalled = false;
  const ip = await discoverServer({
    hostname: "exam-server", timeoutMs: 100, cachedIp: "192.168.1.9",
    queryMdns: async () => { mdnsCalled = true; return null; },
    healthCheck: async (x) => x === "192.168.1.9",
  });
  assert.strictEqual(ip, "192.168.1.9");
  assert.strictEqual(mdnsCalled, false);
});

test("falls back to mDNS when no/!healthy cache", async () => {
  const ip = await discoverServer({
    hostname: "exam-server", timeoutMs: 100, cachedIp: null,
    queryMdns: async () => "192.168.1.20",
    healthCheck: async (x) => x === "192.168.1.20",
  });
  assert.strictEqual(ip, "192.168.1.20");
});

test("configured serverIp used before mDNS (server nhà trường IP tĩnh)", async () => {
  let mdnsCalled = false;
  const ip = await discoverServer({
    hostname: "exam-server", configuredIp: "10.0.0.50", timeoutMs: 100, cachedIp: null,
    queryMdns: async () => { mdnsCalled = true; return "10.0.0.99"; },
    healthCheck: async (x) => x === "10.0.0.50",
  });
  assert.strictEqual(ip, "10.0.0.50");
  assert.strictEqual(mdnsCalled, false);   // không cần hỏi mDNS khi IP cấu hình sống
});

test("configured serverIp chết → vẫn rơi xuống mDNS", async () => {
  const ip = await discoverServer({
    hostname: "exam-server", configuredIp: "10.0.0.50", timeoutMs: 100, cachedIp: null,
    queryMdns: async () => "192.168.1.20",
    healthCheck: async (x) => x === "192.168.1.20",   // chỉ IP mDNS sống
  });
  assert.strictEqual(ip, "192.168.1.20");
});

test("returns null when nothing resolves", async () => {
  const ip = await discoverServer({
    hostname: "exam-server", timeoutMs: 100, cachedIp: "1.1.1.1",
    queryMdns: async () => null,
    healthCheck: async () => false,
  });
  assert.strictEqual(ip, null);
});

test("mDNS hit but health fails → null", async () => {
  const ip = await discoverServer({
    hostname: "exam-server", timeoutMs: 100, cachedIp: null,
    queryMdns: async () => "10.0.0.5",
    healthCheck: async () => false,
  });
  assert.strictEqual(ip, null);
});
