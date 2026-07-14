import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import legacy from "@vitejs/plugin-legacy";

// App thí sinh phục vụ tại subpath /thisinh/ qua Caddy (link đăng nhập vai trò
// thí sinh). API nằm riêng ở /api/exam/* — không liên quan tới base này.
//
// Máy thi dùng kiosk Electron (Chromium 108) HOẶC Firefox ESR 115 / Chrome 109
// trên Windows 7. SEB 2.4.1 / Gecko 41 đã bỏ (AD-64/66 — SEB không chạy được
// trên các máy Win7 của trường). Ngưỡng thấp nhất hiện tại: Chromium 108 / FF 115.
//
// plugin-legacy vẫn giữ để transpile ES5 + polyfill cho các trình duyệt cũ
// trong ngưỡng mới (chrome 108, firefox 115). Tailwind v3 bắt buộc — v4 đòi
// Chrome 111+/Firefox 128+ (dùng @property native) nên chưa nâng được. CSS được
// hạ cấp qua postcss (postcss.config.js + postcss-preset-env).
export default defineConfig({
  base: "/thisinh/",
  plugins: [
    react(),
    legacy({
      targets: ["chrome 108", "firefox 115"],
      // Polyfill các tính năng còn thiếu trong ngưỡng mới (Promise/regenerator/
      // v.v.) để React 18 + axios + zustand chạy được.
      polyfills: true,
      modernPolyfills: true,
      renderLegacyChunks: true,
    }),
  ],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    hmr: { clientPort: 80 },
  },
  // App thí sinh chạy bản PRODUCTION build (vite preview) sau Caddy — không dùng
  // dev server (native-ESM không tương thích với các engine cũ trong ngưỡng mục tiêu).
  // allowedHosts:true cho phép preview chấp nhận Host header của Caddy
  // (exam-server.local hoặc IP LAN).
  preview: {
    host: true,
    port: 5173,
    strictPort: true,
    allowedHosts: true,
  },
});
