import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Admin app is served behind Caddy at the /admin/ subpath.
//
// CHẠY BẢN PRODUCTION BUILD (vite preview), KHÔNG dùng dev server nữa — sự cố
// hiện trường 27-07: sau khi nhà trường đặt thêm một lớp webhost/proxy trước
// server, WebSocket HMR của Vite không qua được lớp đó → client Vite mất kết
// nối → nó ping thấy HTTP còn sống → tự `location.reload()` → WS lại đứt →
// TRANG ADMIN REFRESH LIÊN TỤC không dùng được. Bản build không có HMR nên
// không thể lặp, lại nhẹ + nhanh hơn hẳn dev server.
// (Muốn HMR khi phát triển: chạy `npm run dev` trực tiếp trên máy dev.)
export default defineConfig({
  base: "/admin/",
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    allowedHosts: true,
  },
  // allowedHosts:true để preview chấp nhận Host header bất kỳ (IP LAN, tên miền
  // trường, exam-server.local) do Caddy/webhost chuyển tới.
  preview: {
    host: true,
    port: 5173,
    strictPort: true,
    allowedHosts: true,
  },
});
