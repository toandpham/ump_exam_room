import { useEffect, useState } from "react";
import { NotebookPen, X } from "lucide-react";

// Giấy nháp theo TỪNG câu hỏi cho thí sinh. Chỉ lưu cục bộ (localStorage trên máy
// thi), KHÔNG gửi server, KHÔNG tính điểm. Tự xoá khi nộp/kết thúc (xem clearNotes,
// gọi từ ExamScreen). Khoá theo session để reload giữa giờ vẫn còn nháp.
const keyFor = (sid: string) => `exam_notes_${sid}`;

function loadAll(sid: string): Record<string, string> {
  try {
    const v = JSON.parse(localStorage.getItem(keyFor(sid)) || "{}");
    return v && typeof v === "object" ? v : {};
  } catch {
    return {};
  }
}

/** Xoá toàn bộ giấy nháp của phiên thi (gọi khi nộp bài / hết giờ). */
export function clearNotes(sid: string) {
  try {
    localStorage.removeItem(keyFor(sid));
  } catch {
    /* ignore */
  }
}

interface Props {
  open: boolean;
  onClose: () => void;
  sessionId: string;
  questionId: string;
  questionNumber: number;
}

export default function QuestionNotes({ open, onClose, sessionId, questionId, questionNumber }: Props) {
  const [text, setText] = useState("");

  // Nạp nháp của câu hiện tại mỗi khi đổi câu (hoặc đổi phiên).
  useEffect(() => {
    setText(loadAll(sessionId)[questionId] || "");
  }, [sessionId, questionId]);

  function onChange(v: string) {
    setText(v);
    const all = loadAll(sessionId);
    if (v.trim()) all[questionId] = v;
    else delete all[questionId];
    try {
      localStorage.setItem(keyFor(sessionId), JSON.stringify(all));
    } catch {
      /* ignore (vd hết quota) */
    }
  }

  if (!open) return null;

  // w-64: mở cùng lúc 3 công cụ (nháp + máy tính + tham chiếu) vẫn còn chỗ cho đề.
  return (
    <aside className="w-64 shrink-0 h-full bg-white border-l border-slate-200 flex flex-col select-none">
      <div className="flex items-center justify-between px-3 py-2 bg-amber-500 text-white">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <NotebookPen size={15} /> Giấy nháp — Câu {questionNumber}
        </div>
        <button onClick={onClose} title="Đóng" className="hover:bg-amber-600 rounded p-1">
          <X size={16} />
        </button>
      </div>

      <div className="p-3 flex-1 flex flex-col gap-2 min-h-0">
        <textarea
          value={text}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Ghi nháp cho câu này… (chỉ lưu trên máy, tự xoá khi nộp bài)"
          className="flex-1 w-full resize-none rounded-lg border border-slate-300 p-3 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-amber-400"
        />
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-slate-400">Nháp riêng từng câu · không tính điểm</span>
          {text.trim() && (
            <button onClick={() => onChange("")} className="text-xs text-rose-600 hover:underline">
              Xoá nháp câu này
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
