"use strict";
const { app, BrowserWindow, ipcMain, globalShortcut, session } = require("electron");
const path = require("path");
const fs = require("fs");
const { execFile, execFileSync, spawn } = require("child_process");

const { loadConfig } = require("./config");
const { discoverServer, queryMdns, healthCheck } = require("./discovery");
const { startPolling, fetchCommand } = require("./control");
const { checkForUpdate, fetchText, downloadFile } = require("./updater");
const { isBlockedKey, KIOSK_WINDOW_OPTS } = require("./lockdown");
const { handleEmergencyVerify } = require("./quit");

// --- Tắt tăng tốc GPU ---
// Một số máy Win10 (driver đồ hoạ cũ, vd Acer/Intel tích hợp) làm Chromium crash
// ngay lúc khởi tạo ANGLE/Direct3D → Application Error 0x80000003 (app mở không
// lên). Tắt tăng tốc GPU để render bằng CPU (SwiftShader) — app này nhẹ nên không
// ảnh hưởng hiệu năng. PHẢI gọi trước khi app sẵn sàng (ngay đầu module).
app.disableHardwareAcceleration();
app.commandLine.appendSwitch("disable-gpu");
app.commandLine.appendSwitch("disable-gpu-compositing");

// --- Khởi động được trên Win10 có phần mềm bảo mật chèn DLL ---
// Nhiều máy Win10 (AV/endpoint chèn DLL chưa ký vào tiến trình Chromium) crash
// ngay lúc mở: Application Error 0x80000003 — dù Win7/Win11 chạy tốt. Tắt
// RendererCodeIntegrity (Chromium thôi đòi DLL ký bởi Microsoft) + bỏ sandbox để
// không bị AV giết tiến trình. Máy thi LAN tin cậy nên đánh đổi này chấp nhận được.
app.commandLine.appendSwitch("disable-features", "RendererCodeIntegrity");
// LƯU Ý (AD-76): --no-sandbox tắt sandbox Chromium TOÀN CỤC — cờ webPreferences
// sandbox:true trong lockdown.js không còn tác dụng chừng nào switch này còn.
// Đánh đổi CÓ Ý THỨC: máy Win10 thật (AV chèn DLL) từng crash 0x80000003 nếu
// thiếu nó. Bù đắp: contextIsolation + guard điều hướng same-origin + IPC chỉ
// nhận từ splash + server thuộc LAN tin cậy. Thử gỡ lại khi đổi thế hệ máy thi.
app.commandLine.appendSwitch("no-sandbox");

// --- vị trí file cạnh app (portable) ---
function appDir() {
  return process.env.PORTABLE_EXECUTABLE_DIR || path.dirname(app.getPath("exe"));
}
const cfg = loadConfig(path.join(appDir(), "kiosk.config.json"));
const cacheFile = path.join(app.getPath("userData"), "last-ip.json");
// Sentinel: ghi khi ĐÃ áp lockdown registry, xoá khi khôi phục sạch. Nếu còn sót lúc
// khởi động (lần chạy trước crash/bị kill) → tự khôi phục registry trước khi áp lại.
const sentinelFile = path.join(app.getPath("userData"), "lockdown-active");

function readCachedIp() {
  try { return JSON.parse(fs.readFileSync(cacheFile, "utf8")).ip || null; } catch { return null; }
}
function writeCachedIp(ip) {
  try { fs.writeFileSync(cacheFile, JSON.stringify({ ip })); } catch { /* ignore */ }
}
function isValidHost(s) {
  return typeof s === "string" && /^[a-zA-Z0-9.-]{1,255}$/.test(s) && !s.includes("..");
}

// --- Vô hiệu hoá các mục trên màn Ctrl+Alt+Del ---
// Không chặn được màn SAS hiện ra (kernel Windows), nhưng tắt hết lựa chọn nguy
// hiểm: Task Manager, Khoá máy, Đổi mật khẩu, ĐĂNG XUẤT, Tắt máy từ Start.
// QUAN TRỌNG: ghi ở CẢ HKLM (áp cho MỌI user) LẪN HKCU. App chạy elevated
// (requireAdministrator) có thể được nâng quyền bằng MỘT tài khoản admin KHÁC →
// khi đó HKCU là hive của admin, KHÔNG phải thí sinh đang ngồi thi → chính sách
// per-user không có tác dụng (đây là lý do Win7 vẫn Log off/Switch user được).
// Bản HKLM áp cho toàn máy nên đúng user nào cũng dính. Cần admin (đã có). Khôi
// phục khi thoát.
const _POLICY_SUBKEYS = [
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System", "DisableTaskMgr"],
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System", "DisableLockWorkstation"],
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System", "DisableChangePassword"],
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "NoLogoff"],
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "StartMenuLogOff"],
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "NoClose"],
];
function setTaskMgr(disabled) {   // tên giữ nguyên cho các call site; nay gồm nhiều policy
  if (process.platform !== "win32") return;
  for (const hive of ["HKLM", "HKCU"]) {
    for (const [sub, name] of _POLICY_SUBKEYS) {
      const key = `${hive}\\${sub}`;
      const args = disabled
        ? ["add", key, "/v", name, "/t", "REG_DWORD", "/d", "1", "/f"]
        : ["delete", key, "/v", name, "/f"];
      // ĐỒNG BỘ: khôi phục policy phải chạy XONG trước khi app.quit() (tránh race
      // khiến nút Shut Down không hiện lại sau khi thoát).
      try { execFileSync("reg", args, { stdio: "ignore" }); } catch { /* ignore */ }
    }
  }
  // Ẩn nút NGUỒN (Shutdown/Restart) trên màn Ctrl+Alt+Del / đăng nhập. Đây là CHÍNH SÁCH
  // MÁY (HKLM) → chỉ áp được khi app chạy bằng quyền Administrator; nếu không có quyền,
  // lệnh thất bại im lặng → IT đặt thủ công 1 lần (xem README "Ẩn nút nguồn").
  const SD = "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System";
  const sdArgs = ["add", SD, "/v", "shutdownwithoutlogon", "/t", "REG_DWORD",
                  "/d", disabled ? "0" : "1", "/f"];   // 0 = ẩn nút nguồn; 1 = mặc định (hiện)
  try { execFileSync("reg", sdArgs, { stdio: "ignore" }); } catch { /* ignore */ }
  // Ẩn "Switch user" (đổi tài khoản) trên màn Ctrl+Alt+Del / đăng nhập (HKLM, admin).
  const suArgs = disabled
    ? ["add", SD, "/v", "HideFastUserSwitching", "/t", "REG_DWORD", "/d", "1", "/f"]
    : ["delete", SD, "/v", "HideFastUserSwitching", "/f"];
  try { execFileSync("reg", suArgs, { stdio: "ignore" }); } catch { /* ignore */ }
}

// AD-77c — KHI THOÁT thì KHỞI ĐỘNG LẠI MÁY, không cố "khôi phục" desktop.
// Lịch sử màn hình lỗi trên Win11 khi thoát: (1) taskkill explorer + spawn lại →
// explorer bị ELEVATED không vẽ được = MÀN ĐEN; (2) chỉ taskkill cậy
// AutoRestartShell → shell không lên = MÀN XANH TRỐNG. Cả hai đều do cố đụng vào
// shell. Giải pháp chắc chắn (user xác nhận "restart xong là bình thường hết"):
// gỡ policy khoá rồi `shutdown /r` → boot lại là desktop/taskbar/mọi thứ sạch sẽ,
// không lỗi trên bất kỳ Win7→11 nào. setTaskMgr(false) chạy TRƯỚC reboot để nếu
// vì lý do gì reboot không diễn ra thì máy vẫn không bị kẹt khoá.
function rebootMachine() {
  if (process.platform !== "win32") return;   // Mac/dev: chỉ thoát app
  // /r = restart, /f = ép đóng app đang chạy, /t 0 = ngay lập tức.
  try { execFileSync("shutdown", ["/r", "/f", "/t", "0"], { stdio: "ignore" }); } catch { /* ignore */ }
}

let win = null;
let emergencyWin = null; // cửa sổ thoát khẩn cấp (sở hữu bởi main, độc lập trang thi)
let stopPolling = null;
let serverBase = null;   // http://<ip>
let quitting = false;    // true khi đang thoát hợp lệ
let keepOnTopTimer = null; // handle setInterval(keepOnTop) để clear khi thoát
let retryTimer = null;   // hẹn giờ thử nạp lại trang khi mất kết nối (did-fail-load)
let failCount = 0;       // số lần nạp trang thi thất bại liên tiếp
const MAX_FAILS = 5;     // sau ngần này lần → quay về splash/nhập IP thủ công

function send(channel, data) { if (win && !win.isDestroyed()) win.webContents.send(channel, data); }

// --- Sentinel lockdown (tự khôi phục khi crash) ---
function markLockdown(active) {
  try {
    if (active) fs.writeFileSync(sentinelFile, String(Date.now()));
    else if (fs.existsSync(sentinelFile)) fs.unlinkSync(sentinelFile);
  } catch { /* ignore */ }
}
function sentinelExists() {
  try { return fs.existsSync(sentinelFile); } catch { return false; }
}

// Giữ cửa sổ thi phủ kín màn hình + trên cùng (che taskbar) và GIÀNH LẠI sau khi
// thí sinh bấm Ctrl+Alt+Del rồi Esc (Windows hạ z-order, taskbar lộ ra). KHÔNG cướp
// focus khi cửa sổ đang được focus (để không phá gõ phím / modal trong trang) — chỉ
// gọi focus()/moveTop() khi đã MẤT focus (vd vừa thoát màn Ctrl+Alt+Del).
function keepOnTop() {
  if (quitting || !win || win.isDestroyed()) return;
  // Khi cửa sổ thoát khẩn cấp đang mở, KHÔNG giành lại focus (để gõ được mật khẩu).
  if (emergencyWin && !emergencyWin.isDestroyed()) return;
  try {
    win.setAlwaysOnTop(true, "screen-saver");
    win.setKiosk(true);
    if (win.isMinimized()) win.restore();
    if (!win.isFocused()) { win.moveTop(); win.focus(); }
  } catch (_e) { /* ignore */ }
}

// --- Cửa sổ thoát khẩn cấp (break-glass) độc lập với trang đã nạp ---
// QUAN TRỌNG: sau khi vào trang thi (React từ server), renderer KHÔNG còn IPC kiosk,
// nên modal phải do MAIN tạo bằng file:// + preload riêng → vẫn thoát được kể cả khi
// server/mạng hỏng (đúng lúc cần break-glass nhất).
function openEmergencyWindow() {
  if (quitting) return;
  if (emergencyWin && !emergencyWin.isDestroyed()) { emergencyWin.focus(); return; }
  emergencyWin = new BrowserWindow({
    width: 380, height: 240, frame: false, resizable: false, movable: false,
    alwaysOnTop: true, skipTaskbar: true, parent: win || undefined, modal: false, show: false,
    webPreferences: {
      contextIsolation: true, nodeIntegration: false, sandbox: true, devTools: false,
      preload: path.join(__dirname, "emergency-preload.js"),
    },
  });
  emergencyWin.removeMenu();
  emergencyWin.setAlwaysOnTop(true, "screen-saver");
  emergencyWin.loadFile(path.join(__dirname, "emergency.html"));
  emergencyWin.once("ready-to-show", () => {
    if (!emergencyWin || emergencyWin.isDestroyed()) return;
    emergencyWin.center();
    emergencyWin.show();
    emergencyWin.moveTop();
    emergencyWin.focus();
  });
  emergencyWin.on("closed", () => { emergencyWin = null; });
}
function closeEmergencyWindow() {
  if (emergencyWin && !emergencyWin.isDestroyed()) { try { emergencyWin.close(); } catch { /* ignore */ } }
  emergencyWin = null;
}

// --- Bộ chặn phím native (Win/Alt+Tab/Ctrl+Esc…) ---
let keyBlocker = null;
function keyBlockerPath() {
  const candidates = [
    path.join(process.resourcesPath || "", "keyblocker.exe"),
    path.join(__dirname, "..", "resources", "keyblocker.exe"),
  ];
  return candidates.find((p) => { try { return fs.existsSync(p); } catch { return false; } });
}
function startKeyBlocker() {
  if (process.platform !== "win32") return;     // chỉ Windows (Mac dev không có → im lặng)
  const exe = keyBlockerPath();
  if (!exe) {
    // CẢNH BÁO TO: thiếu keyblocker.exe → KHÔNG chặn được Win/Alt+Tab/Ctrl+Esc (khoá máy cốt lõi TẮT).
    console.error("=".repeat(70));
    console.error("[KIOSK] CẢNH BÁO NGHIÊM TRỌNG: KHÔNG tìm thấy keyblocker.exe!");
    console.error("[KIOSK] Phím hệ thống (Windows, Alt+Tab, Ctrl+Esc...) SẼ KHÔNG bị chặn.");
    console.error("[KIOSK] Build keyblocker.exe (xem native/keyblocker.c) và đặt vào resources/.");
    console.error("=".repeat(70));
    return;
  }
  try {
    keyBlocker = spawn(exe, [String(process.pid)], { detached: false, stdio: "ignore", windowsHide: true });
  } catch (_e) { /* ignore */ }
}
function stopKeyBlocker() {
  if (keyBlocker && !keyBlocker.killed) { try { keyBlocker.kill(); } catch { /* ignore */ } }
  keyBlocker = null;
}

async function wipeKiosk() {
  // SP-4: xoá đề + đáp án local (HTTP cache + storage) rồi về đăng nhập. Âm thầm.
  if (quitting || !win || win.isDestroyed()) return;
  try {
    const ses = win.webContents.session;
    await ses.clearCache();
    await ses.clearStorageData();
  } catch (_e) { /* ignore */ }
  if (!quitting && win && !win.isDestroyed() && serverBase) {
    win.loadURL(serverBase + cfg.path);
  }
}

function quitKiosk() {
  quitting = true;
  if (keepOnTopTimer) { clearInterval(keepOnTopTimer); keepOnTopTimer = null; }
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
  if (manualRetryTimer) { clearTimeout(manualRetryTimer); manualRetryTimer = null; }
  closeEmergencyWindow();
  stopKeyBlocker();
  if (stopPolling) stopPolling();
  setTaskMgr(false);   // gỡ policy khoá TRƯỚC khi reboot → máy về bình thường sau boot
  markLockdown(false);
  rebootMachine();     // AD-77c — reboot thay vì cố khôi phục desktop (tránh màn đen/xanh Win11)
  app.quit();
}

let manualRetryTimer = null; // tự tìm lại nền khi đang kẹt màn nhập IP

async function runDiscovery(quiet = false) {
  if (manualRetryTimer) { clearTimeout(manualRetryTimer); manualRetryTimer = null; }
  if (!quiet) send("kiosk:status", { phase: "searching" });
  const ip = await discoverServer({
    hostname: cfg.serverHost, configuredIp: cfg.serverIp, timeoutMs: cfg.discoveryTimeoutMs,
    queryMdns, healthCheck, cachedIp: readCachedIp(),
  });
  if (ip) { proceed(ip); return; }
  if (!quiet) send("kiosk:status", { phase: "manual" });
  // AD-76: máy boot nhanh hơn DHCP/switch từng kẹt vĩnh viễn ở màn nhập IP chờ
  // người bấm "Tìm lại" — giờ tự tìm lại NỀN mỗi 10s (quiet: không đổi UI, không
  // phá form đang gõ; thấy server là tự vào).
  if (!quitting && !serverBase) {
    manualRetryTimer = setTimeout(() => runDiscovery(true), 10000);
  }
}

async function proceed(ip) {
  writeCachedIp(ip);
  serverBase = `http://${ip}`;
  failCount = 0;
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
  if (manualRetryTimer) { clearTimeout(manualRetryTimer); manualRetryTimer = null; }

  // AD-84: kiểm tra cập nhật kiosk TRƯỚC khi vào đề (an toàn — chưa thi). Toàn bộ
  // bọc fail-safe: mọi lỗi → vào đề bằng bản hiện tại, KHÔNG bao giờ chặn thi.
  try {
    const upd = await checkForUpdate({
      serverBase, currentVersion: app.getVersion(), fetchText,
    });
    if (upd && (await runSelfUpdate(upd))) return;   // đang tải+cài → không load đề
  } catch (_e) { /* fail-safe */ }

  loadExam();
}

function loadExam() {
  if (quitting || !win || win.isDestroyed() || !serverBase) return;
  win.loadURL(serverBase + cfg.path);
  // Poll lệnh thoát/wipe từ server.
  if (stopPolling) stopPolling();
  stopPolling = startPolling({
    getter: () => fetchCommand(serverBase),
    intervalMs: cfg.controlPollMs,
    onQuit: quitKiosk,
    onWipe: wipeKiosk,
  });
}

// AD-84: có bản mới → tải file cài từ server + cài im lặng (/S) + thoát để bản mới
// thay & tự chạy lại. Trả true nếu ĐÃ bắt đầu cập nhật (đừng load đề nữa). Chỉ chạy
// khi ở splash (chưa thi). KHÔNG reboot (khác quitKiosk). Fail-safe: lỗi → false.
async function runSelfUpdate(upd) {
  if (process.platform !== "win32") return false;   // chỉ cài .exe trên Windows
  try {
    send("kiosk:status", { phase: "updating", version: upd.version });
    const tmp = path.join(app.getPath("temp"), "UMP_ExamKiosk-Update.exe");
    // downloadFile kiểm SHA-256 khớp manifest ĐÃ KÝ — lệch hash thì reject (không cài).
    await downloadFile(upd.url, tmp, { sha256: upd.sha256 });
    // NSIS cài im lặng: tự đóng app cũ, cài đè, (mặc định) chạy lại app sau khi xong.
    spawn(tmp, ["/S"], { detached: true, stdio: "ignore" }).unref();
    // Nhường ~1.5s cho installer khởi động rồi tự thoát để nó thay được file .exe.
    setTimeout(quitForUpdate, 1500);
    return true;
  } catch (_e) {
    return false;   // tải/cài lỗi → vào đề bản hiện tại
  }
}

// Thoát để cập nhật: dọn như quitKiosk NHƯNG KHÔNG reboot (installer sẽ chạy lại app).
// Vẫn gỡ policy khoá phòng khi bản mới không tự chạy lại → máy không kẹt Task Manager.
function quitForUpdate() {
  quitting = true;
  if (keepOnTopTimer) { clearInterval(keepOnTopTimer); keepOnTopTimer = null; }
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
  if (manualRetryTimer) { clearTimeout(manualRetryTimer); manualRetryTimer = null; }
  closeEmergencyWindow();
  stopKeyBlocker();
  if (stopPolling) stopPolling();
  setTaskMgr(false);
  markLockdown(false);
  app.quit();
}

function applyLockdown(wc) {
  // Chặn phím.
  wc.on("before-input-event", (event, input) => {
    // Lối thoát khẩn cấp Ctrl+Alt+Shift+Q.
    if (input.type === "keyDown" && input.control && input.alt && input.shift &&
        (input.key || "").toUpperCase() === "Q") {
      event.preventDefault();
      openEmergencyWindow();   // modal do MAIN tạo → hoạt động kể cả sau khi vào trang thi
      return;
    }
    if (isBlockedKey(input)) event.preventDefault();
  });
  // Không cho mở cửa sổ/popup mới.
  wc.setWindowOpenHandler(() => ({ action: "deny" }));
  // Chỉ cho điều hướng tới đúng origin máy chủ; trước khi biết máy chủ chỉ cho splash (file://).
  const sameOriginGuard = (event, url) => {
    let u;
    try { u = new URL(url); } catch (_e) { event.preventDefault(); return; }
    if (!serverBase) {
      // Splash phase: only the local splash file is expected.
      if (u.protocol === "file:") return;
      event.preventDefault();
      return;
    }
    try {
      const sb = new URL(serverBase);
      if (u.protocol === sb.protocol && u.host === sb.host) return; // same-origin only
    } catch (_e) { /* fall through to block */ }
    event.preventDefault();
  };
  wc.on("will-navigate", sameOriginGuard);
  wc.on("will-redirect", sameOriginGuard);   // chặn cả chuyển hướng phía server/HTTP

  // AD-76: renderer crash/treo (máy cũ ít RAM + render CPU vì GPU đã tắt) —
  // did-fail-load KHÔNG bắn cho crash nên trước đây thành màn TRẮNG CHẾT giữ
  // trên cùng tới khi giám thị thoát khẩn cấp. Nạp lại trang là an toàn: đáp án
  // đã lưu server-side, thí sinh đăng nhập lại làm tiếp.
  wc.on("render-process-gone", (_e, details) => {
    if (quitting || !win || win.isDestroyed()) return;
    if (details && details.reason === "clean-exit") return;
    if (serverBase) win.loadURL(serverBase + cfg.path);
    else win.loadFile(path.join(__dirname, "splash.html"));
  });
  wc.on("unresponsive", () => {
    // Treo > ngưỡng của Electron → ép crash renderer; handler trên nạp lại.
    if (quitting || !win || win.isDestroyed() || !serverBase) return;
    try { wc.forcefullyCrashRenderer(); } catch (_e) { /* ignore */ }
  });

  // Mất kết nối sau khi đã vào trang thi → tự thử lại (backoff), quá MAX_FAILS → về splash.
  wc.on("did-fail-load", (_e, errorCode, _desc, _validatedURL, isMainFrame) => {
    if (!isMainFrame) return;          // chỉ quan tâm khung chính
    if (!serverBase) return;           // đang ở splash → KHÔNG retry-loop
    if (errorCode === -3) return;      // ERR_ABORTED (do điều hướng/người dùng) → bỏ qua
    failCount += 1;
    if (failCount >= MAX_FAILS) {
      failCount = 0;
      revertToSplash();
      return;
    }
    if (retryTimer) clearTimeout(retryTimer);
    const delay = Math.min(2000 * failCount, 10000);   // backoff: 2s,4s,6s,8s… cap 10s
    retryTimer = setTimeout(() => {
      if (quitting || !serverBase || !win || win.isDestroyed()) return;
      win.loadURL(serverBase + cfg.path);
    }, delay);
  });
}

// Quay về màn splash/nhập IP khi mất kết nối kéo dài.
function revertToSplash() {
  if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
  serverBase = null;
  if (stopPolling) { stopPolling(); stopPolling = null; }
  if (win && !win.isDestroyed()) win.loadFile(path.join(__dirname, "splash.html"));
}

function createWindow() {
  win = new BrowserWindow({
    ...KIOSK_WINDOW_OPTS,
    webPreferences: { ...KIOSK_WINDOW_OPTS.webPreferences, preload: path.join(__dirname, "preload.js") },
  });
  win.removeMenu();
  applyLockdown(win.webContents);
  // Giữ cửa sổ LUÔN PHỦ KÍN taskbar + giành lại sau Ctrl+Alt+Del. (An toàn vì app
  // KHÔNG còn dùng hộp thoại gốc của Windows — mọi confirm đều là modal TRONG TRANG,
  // nên việc giữ-trên-cùng này không phá hộp thoại nào. keyblocker.exe lo chặn phím.)
  win.on("blur", keepOnTop);
  win.on("minimize", keepOnTop);
  keepOnTopTimer = setInterval(keepOnTop, 600);
  win.loadFile(path.join(__dirname, "splash.html"));
  win.webContents.on("did-finish-load", () => {
    const url = win.webContents.getURL();
    // AD-76: khoá zoom Ctrl+lăn-chuột (phím Ctrl+/- đã chặn nhưng wheel thì chưa
    // — thí sinh zoom vỡ layout đề).
    try { win.webContents.setVisualZoomLevelLimits(1, 1); } catch (_e) { /* ignore */ }
    // chỉ chạy discovery khi đang ở splash (không phải sau khi vào trang thi)
    if (url.startsWith("file://")) {
      // Hiện số phiên bản trên splash để giám thị đối chiếu khi hỗ trợ từ xa.
      send("kiosk:version", app.getVersion());
      runDiscovery();
    }
    else if (serverBase && url.startsWith(serverBase)) failCount = 0; // nạp trang thi OK → reset đếm lỗi
  });
}

// --- IPC từ renderer ---
// AD-76: preload gắn theo WebContents nên window.kiosk tồn tại cả TRONG trang thi
// — chỉ nhận lệnh từ splash (file://) để trang thi bị XSS không thể chuyển kiosk
// sang server khác qua submitIp.
function fromSplash(event) {
  try { return String(event.sender.getURL() || "").startsWith("file://"); }
  catch (_e) { return false; }
}
ipcMain.on("kiosk:manual-ip", async (e, ip) => {
  if (!fromSplash(e)) return;
  if (!isValidHost(ip)) {
    send("kiosk:status", { phase: "manual", error: "Địa chỉ không hợp lệ." });
    return;
  }
  if (await healthCheck(ip)) proceed(ip);
  else send("kiosk:status", { phase: "manual", error: "Không kết nối được máy chủ ở IP này." });
});
ipcMain.on("kiosk:retry", (e) => { if (fromSplash(e)) runDiscovery(); });
// Verify mật khẩu thoát khẩn cấp (từ cửa sổ emergency do main tạo). Đúng → thoát app.
// AD-76: chỉ nhận từ đúng cửa sổ emergency + phạt 1.5s sau mỗi lần sai (chống thí
// sinh ngồi dò mật khẩu bằng script trong trang thi hoặc gõ tay tốc độ cao).
ipcMain.handle("kiosk:emergency-verify", async (e, pw) => {
  if (!emergencyWin || emergencyWin.isDestroyed() || e.sender !== emergencyWin.webContents) {
    return false;
  }
  const ok = handleEmergencyVerify(pw, cfg.emergencyPassword,
    () => { closeEmergencyWindow(); quitKiosk(); });
  if (!ok) await new Promise((r) => setTimeout(r, 1500));
  return ok;
});
ipcMain.on("kiosk:emergency-cancel", () => closeEmergencyWindow());

// --- single instance ---
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => { if (win) win.focus(); });
  app.whenReady().then(() => {
    // AD-91: đóng dấu MỌI request bằng header riêng để máy chủ nhận ra đây là phần
    // mềm thi (chỉ kiosk mới được làm bài; trình duyệt thường bị 403). Máy chủ còn
    // nhận diện dự phòng qua chuỗi "Electron/" trong User-Agent nên các bản kiosk cũ
    // vẫn thi được — header này là đường nhận diện chính cho bản mới.
    session.defaultSession.webRequest.onBeforeSendHeaders((details, cb) => {
      cb({ requestHeaders: { ...details.requestHeaders, "X-Exam-Kiosk": app.getVersion() } });
    });
    // Tự khôi phục sau crash: nếu lần chạy trước để sót lockdown (sentinel còn) → gỡ trước.
    if (sentinelExists()) setTaskMgr(false);
    setTaskMgr(true);
    markLockdown(true);
    startKeyBlocker();
    createWindow();
    // Đăng ký nuốt mọi tổ hợp có thể ở tầng hệ thống (best-effort: một số tổ hợp
    // Windows giữ riêng — RegisterHotKey sẽ thất bại, ta bỏ qua; tuyến chính vẫn là
    // refocus() ở trên).
    const accels = [
      // chuyển/đóng cửa sổ
      "Alt+Tab", "Alt+Shift+Tab", "Super+Tab", "Alt+Escape", "Control+Escape",
      "Alt+F4", "Alt+Space",
      // phím Windows
      "Super+D", "Super+E", "Super+R", "Super+M", "Super+L", "Super+S", "Super+X",
      "Super+I", "Super+A", "Super+B", "Super+Period", "Super+Up", "Super+Down",
      "Super+Left", "Super+Right",
      // trình duyệt: tab/cửa sổ/in/lưu/mở/nguồn/zoom/devtools
      "Control+W", "Control+Shift+W", "Control+T", "Control+Shift+T", "Control+N",
      "Control+Shift+N", "Control+P", "Control+S", "Control+O", "Control+U",
      "Control+R", "Control+Shift+R", "Control+Plus", "Control+-", "Control+0",
      "Control+Shift+I", "Control+Shift+J", "Control+Shift+C", "Control+Shift+K",
      "Control+Shift+Delete",
      // phím chức năng + chụp màn hình
      "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
      "PrintScreen", "Alt+PrintScreen",
    ];
    for (const acc of accels) {
      try { globalShortcut.register(acc, () => {}); } catch { /* ignore */ }
    }
  });
  app.on("will-quit", () => {
    globalShortcut.unregisterAll();
    if (keepOnTopTimer) { clearInterval(keepOnTopTimer); keepOnTopTimer = null; }
    if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
    setTaskMgr(false);
    markLockdown(false);
    stopKeyBlocker();
  });
  app.on("window-all-closed", () => app.quit());
}
