"use strict";
const { test } = require("node:test");
const assert = require("node:assert");
const crypto = require("crypto");
const http = require("http");
const os = require("os");
const path = require("path");
const fs = require("fs");
const { parseVersion, isNewer, verifyManifest, checkForUpdate, downloadFile } = require("../src/updater");

// Cặp khoá EPHEMERAL cho test (không phải khoá thật). Ký như nhà cung cấp.
const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
const PUB_HEX = publicKey.export({ format: "der", type: "spki" }).slice(-32).toString("hex");
const signB64 = (msg) => crypto.sign(null, Buffer.from(msg, "utf8"), privateKey).toString("base64url");

test("parseVersion + isNewer (so theo số)", () => {
  assert.deepStrictEqual(parseVersion("1.2.3"), [1, 2, 3]);
  assert.strictEqual(isNewer("1.10.0", "1.9.0"), true);   // 10 > 9, không so chuỗi
  assert.strictEqual(isNewer("1.1.0", "1.1.0"), false);
  assert.strictEqual(isNewer("1.0.0", "1.1.0"), false);
});

test("verifyManifest: chữ ký đúng → true; sửa 1 ký tự / sai khoá → false", () => {
  const raw = '{"version":"1.2.0","file":"a.exe","sha256":"x"}';
  const sig = signB64(raw);
  assert.strictEqual(verifyManifest(raw, sig, PUB_HEX), true);
  assert.strictEqual(verifyManifest(raw + " ", sig, PUB_HEX), false);   // đổi nội dung
  const other = crypto.generateKeyPairSync("ed25519").publicKey
    .export({ format: "der", type: "spki" }).slice(-32).toString("hex");
  assert.strictEqual(verifyManifest(raw, sig, other), false);          // sai khoá
  assert.strictEqual(verifyManifest(raw, "rác", PUB_HEX), false);       // sig hỏng
});

const H64 = "a".repeat(64);   // sha256 hex hợp lệ (giả)
function manifest(v, file = "Setup.exe", sha = H64) {
  const raw = JSON.stringify({ version: v, file, sha256: sha });
  return { raw, sig: signB64(raw) };
}
function fetcherFor(v, file, sha) {
  const { raw, sig } = manifest(v, file, sha);
  return async (url) => (url.endsWith(".sig") ? sig : raw);
}
const realVerify = (raw, sig) => verifyManifest(raw, sig, PUB_HEX);

test("checkForUpdate: bản mới ĐÃ KÝ hợp lệ → {version,url,sha256}", async () => {
  const upd = await checkForUpdate({
    serverBase: "http://10.0.0.1", currentVersion: "1.1.0",
    fetchText: fetcherFor("1.2.0"), verify: realVerify,
  });
  assert.deepStrictEqual(upd, {
    version: "1.2.0", url: "http://10.0.0.1/kiosk/Setup.exe", sha256: H64,
  });
});

test("checkForUpdate: bằng/cũ hơn → null", async () => {
  const same = await checkForUpdate({
    serverBase: "http://10.0.0.1", currentVersion: "1.2.0",
    fetchText: fetcherFor("1.2.0"), verify: realVerify,
  });
  assert.strictEqual(same, null);
});

test("BẢO MẬT: chữ ký sai → null (chống server giả / MITM trong LAN)", async () => {
  // Manifest hợp lệ nhưng .sig bị tráo (ký bằng khoá khác) → verify thật trả false.
  const evil = crypto.generateKeyPairSync("ed25519").privateKey;
  const raw = JSON.stringify({ version: "9.9.9", file: "Setup.exe", sha256: H64 });
  const badSig = crypto.sign(null, Buffer.from(raw), evil).toString("base64url");
  const upd = await checkForUpdate({
    serverBase: "http://10.0.0.1", currentVersion: "1.0.0",
    fetchText: async (u) => (u.endsWith(".sig") ? badSig : raw), verify: realVerify,
  });
  assert.strictEqual(upd, null);
});

test("BẢO MẬT: file lạ (path traversal) / sha256 sai định dạng → null", async () => {
  const trav = await checkForUpdate({
    serverBase: "http://10.0.0.1", currentVersion: "1.0.0",
    fetchText: fetcherFor("2.0.0", "../../evil.exe"), verify: realVerify,
  });
  assert.strictEqual(trav, null);
  const badSha = await checkForUpdate({
    serverBase: "http://10.0.0.1", currentVersion: "1.0.0",
    fetchText: fetcherFor("2.0.0", "Setup.exe", "nothex"), verify: realVerify,
  });
  assert.strictEqual(badSha, null);
});

test("checkForUpdate: fail-safe khi mạng lỗi → null", async () => {
  const netErr = await checkForUpdate({
    serverBase: "http://10.0.0.1", currentVersion: "1.0.0",
    fetchText: async () => { throw new Error("network"); }, verify: realVerify,
  });
  assert.strictEqual(netErr, null);
});

test("downloadFile: đúng SHA-256 → lưu; lệch hash → reject + xoá file", async () => {
  const payload = Buffer.from("EXE-BYTES-xyz");
  const sha = crypto.createHash("sha256").update(payload).digest("hex");
  const server = http.createServer((_req, res) => { res.writeHead(200); res.end(payload); });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const url = `http://127.0.0.1:${server.address().port}/x.exe`;
  const dst = path.join(os.tmpdir(), "kiosk-test-" + process.pid + ".exe");
  try {
    await downloadFile(url, dst, { sha256: sha });
    assert.ok(fs.existsSync(dst));                       // hash đúng → giữ file
    await assert.rejects(downloadFile(url, dst, { sha256: "b".repeat(64) }), /sha256/);
    assert.strictEqual(fs.existsSync(dst), false);       // hash lệch → xoá file
  } finally {
    server.close();
    try { fs.unlinkSync(dst); } catch (_e) { /* */ }
  }
});
