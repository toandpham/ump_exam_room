import { useEffect, useRef, useState } from "react";

interface Props {
  startAt: string;      // ISO — mốc bắt đầu chung (server)
  serverTime: string;   // ISO — giờ server lúc lấy state (để neo, bù lệch đồng hồ máy)
  onStart: () => void;  // gọi khi tới giờ → mở đề
  examName?: string | null;
}

/** Đếm ngược tới mốc bắt đầu CHUNG, neo theo GIỜ SERVER (không theo đồng hồ máy con
 * — tránh lệch giờ giữa các máy). Tới 0 → onStart (mở đề). Đề đã prefetch (SP-2b)
 * nên mở tức thì, mọi máy đồng loạt. */
export default function CountdownScreen({ startAt, serverTime, onStart, examName }: Props) {
  // Bù lệch: offset = giờ_server - giờ_máy tại thời điểm nhận state.
  const offsetRef = useRef(new Date(serverTime).getTime() - Date.now());
  const target = new Date(startAt).getTime();
  const calc = () => Math.max(0, Math.ceil((target - (Date.now() + offsetRef.current)) / 1000));
  const [remaining, setRemaining] = useState(calc);
  const firedRef = useRef(false);
  const fire = () => { if (!firedRef.current) { firedRef.current = true; onStart(); } };

  useEffect(() => {
    if (calc() <= 0) { fire(); return; }
    const id = setInterval(() => {
      const r = calc();
      setRemaining(r);
      if (r <= 0) { clearInterval(id); fire(); }
    }, 250);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-900 text-white p-4 text-center">
      <p className="text-lg text-slate-300">{examName || "Kỳ thi"}</p>
      <p className="mt-2 text-xl">Đề đã sẵn sàng — chuẩn bị bắt đầu</p>
      <div className="mt-8 text-8xl font-bold tabular-nums">{remaining}</div>
      <p className="mt-6 text-slate-400">Bài thi sẽ mở đồng loạt cho tất cả thí sinh</p>
    </div>
  );
}
