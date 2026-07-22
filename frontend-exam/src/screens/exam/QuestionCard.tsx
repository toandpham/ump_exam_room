import { useState } from "react";
import { ChevronLeft, ChevronRight, Send, SkipForward } from "lucide-react";
import type { ExamQuestion } from "../../api/exam";

/** The centered question card: stem + images, the 4 options (positional A/B/C/D
 * labels per QTI — see note below), and the prev / jump-unanswered / next controls.
 * Submit is a floating button bottom-right. Images are click-to-zoom (AD-69). */
export default function QuestionCard({
  q, index, total, answers, unansweredCount, onSelect, onPrev, onNext, onJumpUnanswered, onSubmit,
}: {
  q: ExamQuestion;
  index: number;
  total: number;
  answers: Record<string, string>;
  unansweredCount: number;
  onSelect: (qid: string, opt: string) => void;
  onPrev: () => void;
  onNext: () => void;
  onJumpUnanswered: () => void;
  onSubmit: () => void;
}) {
  // Ảnh đang phóng to (lightbox). null = không phóng.
  const [zoom, setZoom] = useState<string | null>(null);

  return (
    <div className="my-auto w-full">
      <div className="max-w-3xl mx-auto bg-white rounded-xl shadow-sm p-6">
        <div className="flex items-start justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-500">Câu {index + 1}/{total}</h2>
        </div>

        {/* Câu hỏi: ưu tiên — chữ to, rõ (AD-69) */}
        <p className="text-slate-900 text-lg leading-relaxed font-medium mb-4 whitespace-pre-wrap">{q.text}</p>
        {q.images && q.images.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-5">
            {q.images.map((src, i) => (
              <img key={i} src={src} onClick={() => setZoom(src)}
                loading="lazy" decoding="async"
                title="Bấm để phóng to"
                className="max-h-72 rounded border cursor-zoom-in hover:opacity-90" />
            ))}
          </div>
        )}

        {/* Đáp án: nhỏ lại để nhường chỗ cho câu hỏi (AD-69) */}
        <div className="space-y-1.5">
          {q.options.map((o, i) => {
            const selected = answers[q.id] === o.id;
            // Per QTI: the displayed label is POSITIONAL (A,B,C,D top to bottom).
            // Shuffle reorders the option content; the letters never travel. We
            // still submit/score by the option's stable identifier (o.id).
            const label = String.fromCharCode(65 + i);
            return (
              <button key={o.id} onClick={() => onSelect(q.id, o.id)}
                className={`w-full text-left flex items-start gap-2.5 border rounded-lg px-3 py-2 text-sm transition ${selected ? "border-blue-600 bg-blue-50" : "border-slate-200 hover:bg-slate-50"}`}>
                <span className={`w-5 h-5 mt-0.5 shrink-0 rounded-full flex items-center justify-center text-xs font-semibold ${selected ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600"}`}>{label}</span>
                <span className="flex-1 whitespace-pre-wrap">{o.text}</span>
                {o.images && o.images.length > 0 && (
                  <span className="flex flex-wrap gap-1 shrink-0">
                    {o.images.map((src, i) => (
                      <img key={i} src={src}
                        loading="lazy" decoding="async"
                        onClick={(e) => { e.stopPropagation(); setZoom(src); }}
                        title="Bấm để phóng to"
                        className="h-10 rounded border cursor-zoom-in hover:opacity-90" />
                    ))}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex items-center justify-between mt-6 gap-2">
          <button disabled={index === 0} onClick={onPrev}
            className="flex items-center gap-1 px-4 py-2 rounded-lg border disabled:opacity-40">
            <ChevronLeft size={18} /> Câu trước
          </button>

          {unansweredCount > 0 && (
            <button
              onClick={onJumpUnanswered}
              title="Nhảy đến câu chưa làm tiếp theo"
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 text-sm font-semibold"
            >
              <SkipForward size={16} />
              <span className="hidden sm:inline">Câu chưa làm</span>
              <span className="bg-rose-600 text-white rounded-full px-1.5 text-xs min-w-[20px] text-center">{unansweredCount}</span>
            </button>
          )}

          {index < total - 1 ? (
            <button onClick={onNext}
              className="flex items-center gap-1 px-4 py-2 rounded-lg border">
              Câu sau <ChevronRight size={18} />
            </button>
          ) : (
            <span className="w-[92px]" />
          )}
        </div>
      </div>

      {/* Nút Nộp bài cố định ở GÓC DƯỚI BÊN PHẢI (AD-69) — luôn hiện, bấm được mọi lúc */}
      <button
        onClick={onSubmit}
        title={unansweredCount > 0 ? `Còn ${unansweredCount} câu chưa trả lời` : "Nộp bài"}
        className="fixed bottom-5 right-5 z-40 flex items-center gap-2 px-6 py-3 rounded-full bg-green-600 text-white font-bold shadow-lg hover:bg-green-700"
      >
        <Send size={20} /> Nộp bài
        {unansweredCount > 0 && (
          <span className="ml-1 bg-white/25 rounded-full px-2 text-xs font-semibold">còn {unansweredCount}</span>
        )}
      </button>

      {/* Lightbox phóng to ảnh — bấm nền để đóng */}
      {zoom && (
        <div
          className="fixed inset-0 z-50 bg-black/85 flex items-center justify-center p-4 cursor-zoom-out"
          onClick={() => setZoom(null)}
        >
          <img src={zoom} className="max-h-full max-w-full rounded shadow-2xl" />
        </div>
      )}
    </div>
  );
}
