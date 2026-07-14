import { SkipForward } from "lucide-react";
import type { ExamQuestion } from "../../api/exam";

/** Left sidebar: progress, jump-to-unanswered, and the numbered question grid
 * (green = answered, gray = not). */
export default function QuestionNavigator({
  questions, answers, current, total, answeredCount, unansweredCount, onSelect, onJumpUnanswered,
}: {
  questions: ExamQuestion[];
  answers: Record<string, string>;
  current: number;
  total: number;
  answeredCount: number;
  unansweredCount: number;
  onSelect: (i: number) => void;
  onJumpUnanswered: () => void;
}) {
  return (
    <aside className="w-44 bg-white border-r p-3 overflow-auto">
      <p className="text-xs text-slate-500 mb-2">Đã làm {answeredCount}/{total}</p>
      {unansweredCount > 0 ? (
        <button
          onClick={onJumpUnanswered}
          title="Nhảy tới câu kế tiếp chưa trả lời"
          className="w-full mb-3 flex items-center justify-between gap-1 px-2 py-1.5 rounded-md bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 text-xs font-semibold animate-pulse"
        >
          <span className="flex items-center gap-1"><SkipForward size={13} /> Chưa làm</span>
          <span className="bg-rose-600 text-white rounded-full px-1.5 min-w-[20px] text-center">{unansweredCount}</span>
        </button>
      ) : (
        <p className="mb-3 text-xs text-green-700 bg-green-50 border border-green-200 rounded px-2 py-1.5 text-center font-semibold">
          ✓ Đã trả lời hết
        </p>
      )}
      <div className="grid grid-cols-4 gap-1.5">
        {questions.map((qq, i) => {
          const color = answers[qq.id] ? "bg-green-600 text-white" : "bg-slate-200 text-slate-600";
          return (
            <button key={qq.id} onClick={() => onSelect(i)}
              className={`h-8 rounded text-sm font-medium ${color} ${i === current ? "ring-2 ring-offset-1 ring-slate-800" : ""}`}>
              {i + 1}
            </button>
          );
        })}
      </div>
      <div className="mt-3 text-xs text-slate-500 space-y-1">
        <Legend color="bg-green-600" label="Đã làm" />
        <Legend color="bg-slate-200" label="Chưa làm" />
      </div>
    </aside>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return <div className="flex items-center gap-2"><span className={`w-3 h-3 rounded ${color}`} /> {label}</div>;
}
