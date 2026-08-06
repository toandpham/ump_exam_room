import { useEffect, useState } from "react";
import { Clock } from "lucide-react";

/** Đồng hồ đếm ngược thời gian thi (AD-78) — dùng chung cho chủ tịch (giám sát
 * buổi) và giám thị (phòng của tôi), hiển thị cùng một giờ.
 *
 * `endTime` = mốc của người kết thúc SỚM NHẤT (ISO). `lastEndTime` = mốc của người
 * kết thúc MUỘN NHẤT. Hai giá trị lệch nhau khi có người vào trễ hoặc được cộng giờ
 * riêng — khi đó hiện thêm dòng "người cuối còn …", vì nhãn "thời gian thi" mà chỉ
 * đọc mốc sớm nhất sẽ khiến chủ tịch tưởng cả phòng sắp hết giờ (lỗ AD-121 #3).
 * Máy chủ đã loại phiên đang tạm dừng khỏi cả hai mốc.
 *
 * `serverTime` = giờ máy chủ lúc trả response (ISO) — dùng để NEO đếm ngược theo
 * đồng hồ server, tránh lệch khi máy admin sai giờ. Poll định kỳ (8–15s) sẽ đồng
 * bộ lại mốc này, giữa 2 lần poll thì tự tick 1s.
 *
 * endTime null → "Chưa bắt đầu"; còn ≤0 → "Đã hết giờ". */
export default function ExamCountdown({ endTime, lastEndTime, serverTime, className = "" }: {
  endTime: string | null;
  lastEndTime?: string | null;
  serverTime: string | null;
  className?: string;
}) {
  const [remainingMs, setRemainingMs] = useState<number | null>(null);
  const [lastRemainingMs, setLastRemainingMs] = useState<number | null>(null);

  useEffect(() => {
    if (!endTime) { setRemainingMs(null); setLastRemainingMs(null); return; }
    const end = new Date(endTime).getTime();
    const last = lastEndTime ? new Date(lastEndTime).getTime() : null;
    // Chênh lệch giữa đồng hồ server và đồng hồ máy này (bù skew).
    const skew = serverTime ? new Date(serverTime).getTime() - Date.now() : 0;
    const tick = () => {
      const nowSrv = Date.now() + skew;
      setRemainingMs(end - nowSrv);
      setLastRemainingMs(last === null ? null : last - nowSrv);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [endTime, lastEndTime, serverTime]);

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

  // Lệch quá 1 phút = thật sự có người thi lâu hơn (vào trễ / được cộng giờ), không
  // phải sai số làm tròn. Dưới ngưỡng đó thì im lặng cho gọn.
  const spread =
    remainingMs !== null && lastRemainingMs !== null && lastRemainingMs - remainingMs > 60_000;

  return (
    <div className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 ${tone} ${className}`}>
      <Clock size={16} className="shrink-0" />
      <span className="text-xs opacity-70">{spread ? "Sớm nhất" : "Thời gian thi"}</span>
      <span className="font-mono font-bold tabular-nums">{label}</span>
      {spread && (
        <span className="text-xs opacity-80 border-l pl-2 ml-0.5"
          title="Có thí sinh vào trễ hoặc được cộng giờ riêng — đây là người kết thúc muộn nhất">
          người cuối <span className="font-mono font-bold tabular-nums">{fmt(lastRemainingMs!)}</span>
        </span>
      )}
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
