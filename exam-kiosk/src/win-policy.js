"use strict";
// Chính sách khoá máy Windows (registry) — tách khỏi main.js ở refactor đợt 3.
// KHÔNG import electron; phần quyết định (`policyCommands`) là hàm THUẦN nên test
// được, phần chạy `reg.exe` nằm ở `applyPolicies`.
//
// --- Vô hiệu hoá các mục trên màn Ctrl+Alt+Del ---
// Không chặn được màn SAS hiện ra (kernel Windows), nhưng tắt hết lựa chọn nguy
// hiểm: Task Manager, Khoá máy, Đổi mật khẩu, ĐĂNG XUẤT, Tắt máy từ Start.
// QUAN TRỌNG: ghi ở CẢ HKLM (áp cho MỌI user) LẪN HKCU. App chạy elevated
// (requireAdministrator) có thể được nâng quyền bằng MỘT tài khoản admin KHÁC →
// khi đó HKCU là hive của admin, KHÔNG phải thí sinh đang ngồi thi → chính sách
// per-user không có tác dụng (đây là lý do Win7 vẫn Log off/Switch user được).
// Bản HKLM áp cho toàn máy nên đúng user nào cũng dính. Cần admin (đã có). Khôi
// phục khi thoát.

const POLICY_SUBKEYS = [
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System", "DisableTaskMgr"],
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System", "DisableLockWorkstation"],
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System", "DisableChangePassword"],
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "NoLogoff"],
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "StartMenuLogOff"],
  ["Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\Explorer", "NoClose"],
];

const SYSTEM_KEY = "HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System";

/** Danh sách tham số `reg.exe` cần chạy để BẬT (disabled=true) hoặc GỠ khoá máy.
 *  Hàm thuần — test kiểm đúng bộ lệnh mà không đụng registry thật. */
function policyCommands(disabled) {
  const cmds = [];
  for (const hive of ["HKLM", "HKCU"]) {
    for (const [sub, name] of POLICY_SUBKEYS) {
      const key = `${hive}\\${sub}`;
      cmds.push(disabled
        ? ["add", key, "/v", name, "/t", "REG_DWORD", "/d", "1", "/f"]
        : ["delete", key, "/v", name, "/f"]);
    }
  }
  // Ẩn nút NGUỒN (Shutdown/Restart) trên màn Ctrl+Alt+Del / đăng nhập. Đây là CHÍNH
  // SÁCH MÁY (HKLM) → chỉ áp được khi app chạy quyền Administrator; không có quyền
  // thì lệnh thất bại im lặng → IT đặt thủ công 1 lần (README "Ẩn nút nguồn").
  // 0 = ẩn nút nguồn; 1 = mặc định (hiện).
  cmds.push(["add", SYSTEM_KEY, "/v", "shutdownwithoutlogon", "/t", "REG_DWORD",
             "/d", disabled ? "0" : "1", "/f"]);
  // Ẩn "Switch user" (đổi tài khoản) trên màn Ctrl+Alt+Del / đăng nhập.
  cmds.push(disabled
    ? ["add", SYSTEM_KEY, "/v", "HideFastUserSwitching", "/t", "REG_DWORD", "/d", "1", "/f"]
    : ["delete", SYSTEM_KEY, "/v", "HideFastUserSwitching", "/f"]);
  return cmds;
}

/** Áp/gỡ chính sách. ĐỒNG BỘ có chủ đích: khôi phục phải xong TRƯỚC app.quit()
 *  (tránh race khiến nút Shut Down không hiện lại sau khi thoát). */
function applyPolicies(disabled, runner) {
  if (process.platform !== "win32") return;
  const run = runner || require("child_process").execFileSync;
  for (const args of policyCommands(disabled)) {
    try { run("reg", args, { stdio: "ignore" }); } catch { /* ignore */ }
  }
}

module.exports = { POLICY_SUBKEYS, policyCommands, applyPolicies };
