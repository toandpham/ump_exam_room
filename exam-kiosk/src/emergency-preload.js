"use strict";
// Preload cho cửa sổ thoát khẩn cấp (độc lập với trang thi đã nạp từ server).
// Chỉ dùng contextBridge + ipcRenderer → tương thích sandbox.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("emergency", {
  // verify trả về Promise<boolean>: true nếu mật khẩu đúng (main sẽ tự thoát app).
  verify: (pw) => ipcRenderer.invoke("kiosk:emergency-verify", pw),
  cancel: () => ipcRenderer.send("kiosk:emergency-cancel"),
});
