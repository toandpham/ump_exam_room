"use strict";
// Tự cập nhật kiosk qua server (AD-84, bảo mật AD-85). Server phát /kiosk/latest.json
// + latest.json.sig + file .exe; kiosk lúc KHỞI ĐỘNG (trước khi thí sinh vào đề):
//   1. Tải latest.json + chữ ký, VERIFY chữ ký Ed25519 bằng khoá công khai NHÚNG SẴN.
//   2. So version; mới hơn → tải .exe, kiểm SHA-256 khớp manifest đã ký.
//   3. Cài im lặng + khởi động lại.
// Vì manifest+hash được ký bằng khoá bí mật offline của nhà cung cấp (KHÔNG có trên
// máy nào khác), kẻ tấn công trong LAN có giả mDNS/đổi IP cũng KHÔNG tạo được bản cập
// nhật hợp lệ → không cần HTTPS (hệ thống offline dùng HTTP theo IP, AD-18/64). Logic
// thuần tách khỏi I/O để test. KHÔNG import electron. Mọi lỗi → bỏ qua (fail-safe:
// chạy tiếp bản hiện tại, KHÔNG bao giờ chặn thi vì update hỏng).
const http = require("http");
const fs = require("fs");
const crypto = require("crypto");

// Khoá CÔNG KHAI của nhà cung cấp (cùng cặp khoá với license — khoá bí mật ở
// ~/.exam-license, ngoài repo). Đổi cặp khoá → thay hex này + backend PUBLIC_KEY_HEX.
const PUBLIC_KEY_HEX = "379b525a08254874b0618e4e5f9907b4f235651fc17c24f2fb7398e1bb5df2e0";

function parseVersion(v) {
  return String(v || "").split(".").map((x) => parseInt(x, 10) || 0);
}

/** server mới hơn local? (so major.minor.patch theo số) */
function isNewer(server, local) {
  const a = parseVersion(server);
  const b = parseVersion(local);
  const n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) {
    const d = (a[i] || 0) - (b[i] || 0);
    if (d !== 0) return d > 0;
  }
  return false;
}

/** Xác minh chữ ký Ed25519 (base64url) trên đúng chuỗi bytes manifest. Sai/lỗi → false. */
function verifyManifest(rawText, sigB64url, publicKeyHex = PUBLIC_KEY_HEX) {
  try {
    const der = Buffer.concat([
      Buffer.from("302a300506032b6570032100", "hex"), // SPKI prefix Ed25519
      Buffer.from(publicKeyHex, "hex"),
    ]);
    const pub = crypto.createPublicKey({ key: der, format: "der", type: "spki" });
    const sig = Buffer.from(String(sigB64url).trim(), "base64url");
    return crypto.verify(null, Buffer.from(rawText, "utf8"), pub, sig);
  } catch (_e) {
    return false;
  }
}

/** Trả {version, url, sha256} nếu server có bản mới hơn ĐÃ KÝ hợp lệ; null nếu không/
 * chữ ký sai/lỗi (fail-safe). `verify` tách ra để test (mặc định verifyManifest thật). */
async function checkForUpdate({ serverBase, currentVersion, fetchText, verify = verifyManifest }) {
  let raw, sig;
  try {
    raw = await fetchText(serverBase + "/kiosk/latest.json");
    sig = await fetchText(serverBase + "/kiosk/latest.json.sig");
  } catch (_e) {
    return null;
  }
  // CHỐT BẢO MẬT: manifest phải có chữ ký hợp lệ của nhà cung cấp mới tin.
  if (!verify(raw, sig)) return null;
  let m;
  try { m = JSON.parse(raw); } catch (_e) { return null; }
  if (!m || !m.version || !m.file || !m.sha256) return null;
  // Defense-in-depth: file phải là tên file .exe đơn giản (dù manifest đã ký) —
  // chặn path traversal (../) / URL lạ lọt vào url tải.
  if (!/^[A-Za-z0-9._-]+\.exe$/.test(m.file)) return null;
  if (!/^[a-f0-9]{64}$/.test(String(m.sha256).toLowerCase())) return null;
  if (!isNewer(m.version, currentVersion)) return null;
  return {
    version: String(m.version),
    url: serverBase + "/kiosk/" + m.file,
    sha256: String(m.sha256).toLowerCase(),
  };
}

// --- I/O thật (main.js dùng) --------------------------------------------------
function fetchText(url, timeoutMs = 4000) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      if (res.statusCode !== 200) { res.resume(); reject(new Error("HTTP " + res.statusCode)); return; }
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => resolve(body));
    });
    req.on("error", reject);
    req.on("timeout", () => { req.destroy(); reject(new Error("timeout")); });
  });
}

/** Tải file về destPath + KIỂM SHA-256 khớp `sha256` (từ manifest đã ký). Lệch hash →
 * xoá file + reject (chống .exe bị tráo). */
function downloadFile(url, destPath, { sha256, timeoutMs = 120000 } = {}) {
  return new Promise((resolve, reject) => {
    const out = fs.createWriteStream(destPath);
    const hash = crypto.createHash("sha256");
    const fail = (e) => { try { out.close(); } catch (_) { /* */ } try { fs.unlinkSync(destPath); } catch (_) { /* */ } reject(e); };
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      if (res.statusCode !== 200) { res.resume(); fail(new Error("HTTP " + res.statusCode)); return; }
      res.on("data", (c) => hash.update(c));
      res.pipe(out);
      out.on("finish", () => out.close(() => {
        const got = hash.digest("hex");
        if (!sha256 || got !== String(sha256).toLowerCase()) { fail(new Error("sha256 mismatch")); return; }
        resolve(destPath);
      }));
    });
    req.on("error", fail);
    req.on("timeout", () => { req.destroy(); fail(new Error("timeout")); });
    out.on("error", fail);
  });
}

module.exports = { parseVersion, isNewer, verifyManifest, checkForUpdate, fetchText, downloadFile, PUBLIC_KEY_HEX };
