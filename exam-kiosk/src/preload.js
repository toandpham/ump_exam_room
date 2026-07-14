"use strict";
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kiosk", {
  // renderer → main
  submitIp: (ip) => ipcRenderer.send("kiosk:manual-ip", ip),
  retry: () => ipcRenderer.send("kiosk:retry"),
  // main → renderer
  // (Thoát khẩn cấp giờ là cửa sổ riêng do main tạo — không còn dùng splash, xem emergency-preload.js)
  onStatus: (cb) => ipcRenderer.on("kiosk:status", (_e, data) => cb(data)),
  onVersion: (cb) => ipcRenderer.on("kiosk:version", (_e, v) => cb(v)),
});
