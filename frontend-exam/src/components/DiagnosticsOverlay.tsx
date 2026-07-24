import { useEffect, useRef, useState } from "react";

/** Bảng CHẨN ĐOÁN hiệu năng (AD-96) — bật/tắt bằng Ctrl+Shift+D (phím này KHÔNG bị
 * kiosk chặn). Mục tiêu: khi máy thi "đơ 2-3s mỗi thao tác", đọc thẳng con số trên
 * màn hình để biết nghẽn ở ĐÂU thay vì đoán:
 *   - GPU: tên bộ vẽ WebGL. Có "SwiftShader/Software" = GPU KHÔNG bật (vẽ bằng CPU);
 *     tên card thật (Intel/AMD/NVIDIA) = GPU đang chạy.
 *   - Trễ bấm→vẽ: thời gian từ lúc bấm tới khung hình kế. Cao (>500ms) = nghẽn luồng chính.
 *   - RAM JS: bộ nhớ heap đang dùng / trần. Gần trần = nghẽn do thiếu RAM (GC liên tục).
 *   - Ảnh data: tổng dung lượng ảnh nhúng base64 trong trang (nếu lớn = ảnh chưa tối ưu).
 * Không đụng gì tới bài thi — chỉ đọc số, hiển thị góc màn hình. */

function webglRenderer(): string {
  try {
    const c = document.createElement("canvas");
    const gl = (c.getContext("webgl") || c.getContext("experimental-webgl")) as WebGLRenderingContext | null;
    if (!gl) return "KHÔNG có WebGL (GPU tắt hoàn toàn)";
    const dbg = gl.getExtension("WEBGL_debug_renderer_info");
    const r = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
    return String(r || "?");
  } catch {
    return "lỗi đọc WebGL";
  }
}

function dataImageBytes(): number {
  let total = 0;
  for (const img of Array.from(document.images)) {
    if (img.src.startsWith("data:")) total += img.src.length;
  }
  return total;
}

export default function DiagnosticsOverlay() {
  const [on, setOn] = useState(false);
  const [, force] = useState(0);   // ép vẽ lại mỗi 0.5s để số liệu cập nhật
  const clickMs = useRef(0);
  const maxMs = useRef(0);
  const gpu = useRef<string>("");

  // Ctrl+Shift+D bật/tắt (không bị lockdown chặn).
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && (e.key === "D" || e.key === "d")) {
        e.preventDefault();
        setOn((v) => { if (!v && !gpu.current) gpu.current = webglRenderer(); return !v; });
      }
    };
    window.addEventListener("keydown", h, true);
    return () => window.removeEventListener("keydown", h, true);
  }, []);

  // Đo trễ bấm→vẽ: bắt click ở pha capture, chờ 2 khung hình rồi tính thời gian.
  useEffect(() => {
    if (!on) return;
    const onClick = () => {
      const t0 = performance.now();
      requestAnimationFrame(() => requestAnimationFrame(() => {
        const dt = performance.now() - t0;
        clickMs.current = Math.round(dt);
        if (dt > maxMs.current) maxMs.current = Math.round(dt);
      }));
    };
    window.addEventListener("click", onClick, true);
    const id = setInterval(() => force((t) => t + 1), 500);
    return () => { window.removeEventListener("click", onClick, true); clearInterval(id); };
  }, [on]);

  if (!on) return null;

  const mem = (performance as any).memory;
  const used = mem ? Math.round(mem.usedJSHeapSize / 1048576) : null;
  const limit = mem ? Math.round(mem.jsHeapSizeLimit / 1048576) : null;
  const imgKB = Math.round(dataImageBytes() / 1024);
  const isSoftware = /swiftshader|software|llvmpipe|microsoft basic/i.test(gpu.current);

  return (
    <div style={{
      position: "fixed", right: 8, bottom: 8, zIndex: 99999,
      background: "rgba(0,0,0,.85)", color: "#fff", font: "12px/1.5 monospace",
      padding: "10px 12px", borderRadius: 8, maxWidth: 360, pointerEvents: "none",
    }}>
      <div style={{ fontWeight: "bold", marginBottom: 4 }}>Chẩn đoán (Ctrl+Shift+D để tắt)</div>
      <div style={{ color: isSoftware ? "#ff6b6b" : "#51cf66" }}>
        GPU: {gpu.current || "?"} {isSoftware ? "← ĐANG VẼ BẰNG CPU!" : "← có tăng tốc"}
      </div>
      <div style={{ color: clickMs.current > 500 ? "#ff6b6b" : "#fff" }}>
        Trễ bấm→vẽ: {clickMs.current} ms (đỉnh {maxMs.current} ms)
      </div>
      <div style={{ color: used != null && limit != null && used > limit * 0.85 ? "#ff6b6b" : "#fff" }}>
        RAM JS: {used != null ? `${used} / ${limit} MB` : "(trình duyệt không cho đọc)"}
      </div>
      <div style={{ color: imgKB > 5000 ? "#ffd43b" : "#fff" }}>
        Ảnh nhúng base64 trong trang: {imgKB} KB
      </div>
    </div>
  );
}
