"use strict";
// Tìm IP server thi. Phần điều phối (discoverServer) thuần & test được; queryMdns/
// healthCheck là I/O thật. KHÔNG import electron.
const http = require("http");
const makeMdns = require("multicast-dns");

async function discoverServer({ hostname, configuredIp, timeoutMs, queryMdns, healthCheck, cachedIp }) {
  // 1. Thử IP đã nhớ (nhanh) nếu còn sống.
  if (cachedIp && (await healthCheck(cachedIp))) return cachedIp;
  // 2. IP/host CẤU HÌNH SẴN (kiosk.config.json → serverIp) — cho server IP tĩnh
  //    của nhà trường, KHÔNG cần mDNS (chạy cả khi switch chặn multicast).
  if (configuredIp && (await healthCheck(configuredIp))) return configuredIp;
  // 3. Hỏi mDNS rồi verify bằng health-check (Mac Bonjour / Linux Avahi = exam-server.local).
  const ip = await queryMdns(hostname, timeoutMs);
  if (ip && (await healthCheck(ip))) return ip;
  return null;
}

function queryMdns(hostname, timeoutMs) {
  return new Promise((resolve) => {
    const m = makeMdns();
    const fqdn = (hostname.endsWith(".local") ? hostname : hostname + ".local").toLowerCase();
    let done = false;
    let timer;
    let requery;
    // Xoá timer + interval khi kết thúc sớm (tránh bộ đếm còn treo sau resolve).
    const finish = (ip) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      clearInterval(requery);
      try { m.destroy(); } catch (_e) { /* ignore */ }
      resolve(ip);
    };
    m.on("response", (res) => {
      const a = (res.answers || []).find(
        (x) => x.type === "A" && String(x.name).toLowerCase() === fqdn);
      if (a) finish(a.data);
    });
    m.on("error", () => finish(null));
    m.query({ questions: [{ name: fqdn, type: "A" }] });
    // AD-76: mDNS là UDP — sáng thi 400 máy bật cùng lúc, 1 gói query rớt là máy
    // đó rơi xuống màn nhập IP tay dù server sống. Phát lại mỗi giây trong cửa sổ
    // timeout (re-transmit theo tinh thần RFC 6762), finish() dọn interval.
    requery = setInterval(() => {
      try { m.query({ questions: [{ name: fqdn, type: "A" }] }); } catch (_e) { /* ignore */ }
    }, 1000);
    timer = setTimeout(() => finish(null), timeoutMs);
  });
}

function healthCheck(ip, timeoutMs = 3000) {
  return new Promise((resolve) => {
    // Guard chống double-resolve khi timeout xảy ra đồng thời với lỗi.
    let settled = false;
    const req = http.get(`http://${ip}/api/health`, { timeout: timeoutMs }, (res) => {
      res.resume();
      if (settled) return;
      settled = true;
      resolve(res.statusCode === 200);
    });
    req.on("error", () => { if (settled) return; settled = true; resolve(false); });
    req.on("timeout", () => { req.destroy(); if (settled) return; settled = true; resolve(false); });
  });
}

module.exports = { discoverServer, queryMdns, healthCheck };
