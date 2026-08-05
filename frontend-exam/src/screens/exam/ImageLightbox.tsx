import { useCallback, useEffect, useRef, useState } from "react";
import { Minus, Plus, X } from "lucide-react";

/** Các mức phóng to (AD-135). Rời rạc thay vì trượt liên tục: bấm là nhảy đúng
 * mức, dễ thao tác bằng chuột trên máy thi và không cần kéo thanh trượt. */
const LEVELS = [1, 1.5, 2, 3, 4];

/** Trình xem ảnh phóng to của màn thi.
 *
 * VÌ SAO VIẾT RIÊNG (thực địa 05-08): bản cũ dùng lưới CSS `place-items-center`
 * với hàng tự co theo nội dung, nên `max-h-full` (100% của hàng) KHÔNG còn giới hạn
 * gì khi ảnh lớn hơn màn hình → ảnh tràn ra ngoài, thí sinh không thấy hết. Nay
 * khung ảnh đo theo **đơn vị màn hình** (vh/vw) nên luôn vừa khung, bất kể ảnh gốc
 * to cỡ nào.
 *
 * Thêm: phóng to nhiều cấp, kéo chuột để xem vùng cần, và nút Đóng rõ ràng.
 * Nút Đóng là BẮT BUỘC chứ không chỉ tiện tay: phần mềm thi chặn phím Esc ở tầng
 * hệ điều hành nên trong phòng thi Esc KHÔNG tới được trang web.
 */
export default function ImageLightbox({
  full, thumb, onClose,
}: { full: string; thumb: string; onClose: () => void }) {
  const [level, setLevel] = useState(0);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const boxRef = useRef<HTMLDivElement | null>(null);
  // Điểm bắt đầu kéo; null = không kéo. `moved` để phân biệt "kéo xong thả tay"
  // với "bấm nền để đóng" — thiếu nó thì kéo hụt ra nền sẽ đóng mất ảnh.
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  const scale = LEVELS[level];
  const zoomed = scale > 1;

  /** Giới hạn kéo theo đúng phần ảnh đang thừa ra, để không kéo ảnh bay khỏi màn. */
  const clamp = useCallback((p: { x: number; y: number }, s: number) => {
    const el = boxRef.current;
    if (!el || s <= 1) return { x: 0, y: 0 };
    const mx = (el.offsetWidth * (s - 1)) / 2;
    const my = (el.offsetHeight * (s - 1)) / 2;
    return {
      x: Math.max(-mx, Math.min(mx, p.x)),
      y: Math.max(-my, Math.min(my, p.y)),
    };
  }, []);

  const setZoom = useCallback((next: number) => {
    const lv = Math.max(0, Math.min(LEVELS.length - 1, next));
    setLevel(lv);
    setPos((p) => clamp(p, LEVELS[lv]));
  }, [clamp]);

  // Esc để đóng — chỉ có tác dụng ngoài phần mềm thi (kiosk chặn Esc), nên nút
  // Đóng vẫn là đường chính.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Lăn chuột để phóng to/thu nhỏ. Phải tự gắn với passive:false mới chặn được
  // việc trang cuộn theo.
  useEffect(() => {
    const el = boxRef.current?.parentElement;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      setLevel((lv) => {
        const next = Math.max(0, Math.min(LEVELS.length - 1, lv + (e.deltaY < 0 ? 1 : -1)));
        setPos((p) => clamp(p, LEVELS[next]));
        return next;
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [clamp]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (!zoomed) return;
    drag.current = { x: e.clientX - pos.x, y: e.clientY - pos.y, moved: false };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    d.moved = true;
    setPos(clamp({ x: e.clientX - d.x, y: e.clientY - d.y }, scale));
  };
  const endDrag = () => { drag.current = null; };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 select-none"
      onClick={() => { if (!drag.current?.moved) onClose(); }}
      role="dialog"
      aria-label="Xem ảnh phóng to"
    >
      {/* Khung ảnh: đo theo màn hình nên KHÔNG BAO GIỜ tràn ra ngoài. */}
      <div
        className="absolute inset-0 flex items-center justify-center overflow-hidden"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <div
          ref={boxRef}
          onClick={(e) => e.stopPropagation()}
          onDoubleClick={() => setZoom(zoomed ? 0 : 2)}
          style={{
            transform: `translate(${pos.x}px, ${pos.y}px) scale(${scale})`,
            cursor: zoomed ? (drag.current ? "grabbing" : "grab") : "zoom-in",
          }}
          className="relative transition-transform duration-100"
        >
          {/* AD-109: bản nhỏ hiện NGAY (đã có sẵn trong bộ nhớ), bản đầy đủ đè lên
              khi tải xong — máy yếu không phải chờ trắng màn. */}
          <img src={thumb} draggable={false}
            className="block max-h-[82vh] max-w-[92vw] rounded shadow-2xl" />
          {full !== thumb && (
            <img src={full} draggable={false}
              className="absolute inset-0 h-full w-full rounded" />
          )}
        </div>
      </div>

      {/* Nút Đóng — luôn thấy, góc trên phải. */}
      <button
        onClick={(e) => { e.stopPropagation(); onClose(); }}
        aria-label="Đóng ảnh"
        className="absolute top-3 right-3 flex items-center gap-1.5 rounded-lg bg-white/90 px-3 py-2 text-sm font-semibold text-slate-800 shadow hover:bg-white"
      >
        <X size={18} /> Đóng
      </button>

      {/* Thanh phóng to, đặt dưới cùng cho dễ với chuột. */}
      <div
        onClick={(e) => e.stopPropagation()}
        className="absolute bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full bg-white/90 px-3 py-1.5 shadow"
      >
        <button onClick={() => setZoom(level - 1)} disabled={level === 0}
          aria-label="Thu nhỏ"
          className="rounded-full p-1.5 text-slate-700 hover:bg-slate-200 disabled:opacity-40">
          <Minus size={18} />
        </button>
        <span className="min-w-[52px] text-center text-sm font-semibold text-slate-800">
          {Math.round(scale * 100)}%
        </span>
        <button onClick={() => setZoom(level + 1)} disabled={level === LEVELS.length - 1}
          aria-label="Phóng to"
          className="rounded-full p-1.5 text-slate-700 hover:bg-slate-200 disabled:opacity-40">
          <Plus size={18} />
        </button>
      </div>

      {zoomed && (
        <p className="pointer-events-none absolute bottom-16 left-1/2 -translate-x-1/2 rounded bg-black/60 px-2 py-1 text-xs text-white">
          Kéo ảnh để xem vùng cần
        </p>
      )}
    </div>
  );
}
