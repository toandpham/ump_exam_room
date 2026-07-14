#!/usr/bin/env node
"use strict";
// Ghi + KÝ manifest phát hành kiosk (AD-85). Chạy trên máy nhà cung cấp (giữ khoá
// bí mật ~/.exam-license/private.key — cùng cặp khoá với license). Tạo:
//   kiosk-release/latest.json      {version, file, sha256}
//   kiosk-release/latest.json.sig  chữ ký Ed25519 (base64url) trên đúng bytes latest.json
// Kiosk verify chữ ký bằng khoá công khai nhúng sẵn (updater.PUBLIC_KEY_HEX) TRƯỚC khi
// tin version/file, rồi kiểm SHA-256 file .exe → LAN attacker không giả được bản cập nhật.
const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");

const version = require("./package.json").version;
const REL = path.join(__dirname, "..", "kiosk-release");
const EXE = "UMP_ExamKiosk-Setup.exe";
const exePath = path.join(REL, EXE);

if (!fs.existsSync(exePath)) {
  console.error(`[sign] Không thấy ${exePath} — chạy 'npm run dist' + copy trước (release.sh lo).`);
  process.exit(1);
}

const seedFile = path.join(os.homedir(), ".exam-license", "private.key");
if (!fs.existsSync(seedFile)) {
  console.error(`[sign] Không thấy khoá bí mật ${seedFile} (giống license-console).`);
  process.exit(1);
}
const seed = fs.readFileSync(seedFile);
if (seed.length !== 32) { console.error("[sign] private.key phải 32 byte."); process.exit(1); }

// SHA-256 file cài
const sha256 = crypto.createHash("sha256").update(fs.readFileSync(exePath)).digest("hex");

// Ghi latest.json (thứ tự khoá cố định — kiosk verify trên ĐÚNG bytes này)
const manifest = JSON.stringify({ version, file: EXE, sha256 }, null, 2) + "\n";
fs.writeFileSync(path.join(REL, "latest.json"), manifest);

// Ký Ed25519 bằng seed (PKCS8 DER wrap)
const der = Buffer.concat([Buffer.from("302e020100300506032b657004220420", "hex"), seed]);
const priv = crypto.createPrivateKey({ key: der, format: "der", type: "pkcs8" });
const sig = crypto.sign(null, Buffer.from(manifest, "utf8"), priv).toString("base64url");
fs.writeFileSync(path.join(REL, "latest.json.sig"), sig + "\n");

// Tự kiểm khoá công khai suy ra khớp bản nhúng trong updater.js
const pubHex = crypto.createPublicKey(priv).export({ format: "der", type: "spki" }).slice(-32).toString("hex");
const { PUBLIC_KEY_HEX } = require("./src/updater");
console.log(`[sign] v${version} · sha256=${sha256.slice(0, 16)}…`);
console.log(`[sign] khoá công khai: ${pubHex}`);
if (pubHex !== PUBLIC_KEY_HEX) {
  console.error("[sign] ⚠️  CẢNH BÁO: khoá công khai KHÔNG khớp updater.PUBLIC_KEY_HEX — kiosk sẽ từ chối bản này!");
  process.exit(1);
}
console.log("[sign] ✅ Đã ghi + ký latest.json (+ .sig).");
