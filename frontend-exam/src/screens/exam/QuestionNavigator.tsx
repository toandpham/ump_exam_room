import { memo } from "react";
import { Flag, SkipForward } from "lucide-react";
import type { ExamQuestion } from "../../api/exam";

/** Left sidebar: progress, jump-to-unanswered, and the numbered question grid
 * (green = answered, gray = not).
 *
 * AD-90b: bọc React.memo — đồng hồ đếm ngược làm màn thi vẽ lại MỖI GIÂY; nếu
 * không chặn ở đây thì cả lưới ~280 nút bị so sánh lại 60 lần/phút, rất tốn CPU
 * trên máy Win7/4GB (kiosk vẽ bằng CPU). Lưới chỉ cần vẽ lại khi đổi đáp án /
 * đổi câu — mọi callback truyền vào đều đã được giữ nguyên danh tính. */
function QuestionNavigator({
  questions, answers, flags, current, total, answeredCount, unansweredCount, flaggedCount,
  onSelect, onJumpUnanswered, onJumpFlagged,
}: {
  questions: ExamQuestion[];
  answers: Record<string, string>;
  /** Câu đang được đánh dấu "cần xem lại" (chỉ lưu trên máy đang thi). */
  flags: Record<string, true>;
  current: number;
  total: number;
  answeredCount: number;
  unansweredCount: number;
  flaggedCount: number;
  onSelect: (i: number) => void;
  onJumpUnanswered: () => void;
  onJumpFlagged: () => void;
}) {
  return (
    <aside className="w-44 bg-white border-r p-3 overflow-auto">
      <p className="text-xs text-slate-500 mb-2">Đã làm {answeredCount}/{total}</p>
      {unansweredCount > 0 ? (
        <button
          onClick={onJumpUnanswered}
          title="Nhảy tới câu kế tiếp chưa trả lời"
          className="w-full mb-3 flex items-center justify-between gap-1 px-2 py-1.5 rounded-md bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 text-xs font-semibold"
        >
          <span className="flex items-center gap-1"><SkipForward size={13} /> Chưa làm</span>
          <span className="bg-rose-600 text-white rounded-full px-1.5 min-w-[20px] text-center">{unansweredCount}</span>
        </button>
      ) : (
        <p className="mb-3 text-xs text-green-700 bg-green-50 border border-green-200 rounded px-2 py-1.5 text-center font-semibold">
          ✓ Đã trả lời hết
        </p>
      )}
      {flaggedCount > 0 && (
        <button
          onClick={onJumpFlagged}
          title="Nhảy tới câu kế tiếp đã đánh dấu xem lại"
          className="w-full mb-3 flex items-center justify-between gap-1 px-2 py-1.5 rounded-md bg-amber-50 hover:bg-amber-100 border border-amber-200 text-amber-700 text-xs font-semibold"
        >
          <span className="flex items-center gap-1"><Flag size={13} /> Cần xem lại</span>
          <span className="bg-amber-500 text-white rounded-full px-1.5 min-w-[20px] text-center">{flaggedCount}</span>
        </button>
      )}
      <div className="grid grid-cols-4 gap-1.5">
        {questions.map((qq, i) => {
          const color = answers[qq.id] ? "bg-green-600 text-white" : "bg-slate-200 text-slate-600";
          // Chấm hổ phách góc trên phải = đã đánh dấu. Dùng CHẤM chứ không đổi màu
          // nền/viền: câu đánh dấu vẫn phải thấy rõ đã làm hay chưa, và viền đang
          // dành cho câu hiện tại.
          return (
            <button key={qq.id} onClick={() => onSelect(i)}
              className={`relative h-8 rounded text-sm font-medium ${color} ${i === current ? "ring-2 ring-offset-1 ring-slate-800" : ""}`}>
              {i + 1}
              {flags[qq.id] && (
                <span
                  data-testid={`flagdot-${i}`}
                  className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-amber-500 border border-white"
                />
              )}
            </button>
          );
        })}
      </div>
      <div className="mt-3 text-xs text-slate-500 space-y-1">
        <Legend color="bg-green-600" label="Đã làm" />
        <Legend color="bg-slate-200" label="Chưa làm" />
        <Legend color="bg-amber-500" label="Cần xem lại" />
      </div>
    </aside>
  );
}

export default memo(QuestionNavigator);

function Legend({ color, label }: { color: string; label: string }) {
  return <div className="flex items-center gap-2"><span className={`w-3 h-3 rounded ${color}`} /> {label}</div>;
}
