import { useEffect, useState } from "react";
import { Clock } from "lucide-react";

/** Đồng hồ đếm ngược thời gian thi CHUNG (AD-78) — dùng chung cho chủ tịch
 * (giám sát buổi) và giám thị (phòng của tôi), hiển thị cùng một giờ.
 *
 * `endTime` = deadline chung (ISO, deadline sớm nhất của cohort đang thi).
 * `serverTime` = giờ máy chủ lúc trả response (ISO) — dùng để NEO đếm ngược theo
 * đồng hồ server, tránh lệch khi máy admin sai giờ. Poll định kỳ (8–15s) sẽ đồng
 * bộ lại mốc này, giữa 2 lần poll thì tự tick 1s.
 *
 * endTime null → "Chưa bắt đầu"; còn ≤0 → "Đã hết giờ". */
export default function ExamCountdown({ endTime, serverTime, className = "" }: {
  endTime: string | null;
  serverTime: string | null;
  className?: string;
}) {
  const [remainingMs, setRemainingMs] = useState<number | null>(null);

  useEffect(() => {
    if (!endTime) { setRemainingMs(null); return; }
    const end = new Date(endTime).getTime();
    // Chênh lệch giữa đồng hồ server và đồng hồ máy này (bù skew).
    const skew = serverTime ? new Date(serverTime).getTime() - Date.now() : 0;
    const tick = () => setRemainingMs(end - (Date.now() + skew));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [endTime, serverTime]);

  let label: string;
  let tone: string;
  if (remainingMs === null) {
    label = "Chưa bắt đầu";
    tone = "bg-slate-100 text-slate-500 border-slate-200";
  } else if (remainingMs <= 0) {
    label = "Đã hết giờ";
    tone = "bg-rose-50 text-rose-700 border-rose-200";
  } else {
    label = fmt(remainingMs);
    // Dưới 5 phút → cảnh báo hổ phách.
    tone = remainingMs <= 5 * 60_000
      ? "bg-amber-50 text-amber-800 border-amber-300"
      : "bg-blue-50 text-blue-800 border-blue-200";
  }

  return (
    <div className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 ${tone} ${className}`}>
      <Clock size={16} className="shrink-0" />
      <span className="text-xs opacity-70">Thời gian thi</span>
      <span className="font-mono font-bold tabular-nums">{label}</span>
    </div>
  );
}

function fmt(ms: number): string {
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}
