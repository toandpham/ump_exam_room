import { memo, useState } from "react";
import { ChevronLeft, ChevronRight, Flag, Send, SkipForward } from "lucide-react";
import type { ExamQuestion } from "../../api/exam";
import { sciText } from "../../lib/sciText";
import ImageLightbox from "./ImageLightbox";

/** The centered question card: stem + images, the 4 options (positional A/B/C/D
 * labels per QTI — see note below), and the prev / jump-unanswered / next controls.
 * Submit is a floating button bottom-right. Images are click-to-zoom (AD-69).
 * AD-90b: memo — khỏi vẽ lại theo mỗi nhịp đồng hồ (xem QuestionNavigator). */
function QuestionCard({
  q, index, total, answers, unansweredCount, flagged, onSelect, onToggleFlag,
  onPrev, onNext, onJumpUnanswered, onSubmit,
}: {
  q: ExamQuestion;
  index: number;
  total: number;
  answers: Record<string, string>;
  unansweredCount: number;
  /** Câu này đang được thí sinh đánh dấu "cần xem lại" (chỉ lưu trên máy). */
  flagged: boolean;
  onSelect: (qid: string, opt: string) => void;
  onToggleFlag: (qid: string) => void;
  onPrev: () => void;
  onNext: () => void;
  onJumpUnanswered: () => void;
  onSubmit: () => void;
}) {
  // Ảnh đang phóng to (lightbox). null = không phóng. AD-109: giữ CẢ bản nhỏ —
  // hiện ngay bản nhỏ (đã giải nén sẵn), bản đầy đủ đè lên khi tải xong; máy 4GB
  // không còn khựng lúc mở/đóng zoom vì tấm to chỉ 1280px (vừa màn 1366×768).
  const [zoom, setZoom] = useState<{ full: string; thumb: string } | null>(null);

  return (
    <div className="my-auto w-full">
      <div className="max-w-3xl mx-auto bg-white rounded-xl shadow-sm p-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-500">Câu {index + 1}/{total}</h2>
          {/* Đánh dấu để quay lại sau. Ghi chú riêng của thí sinh — không gửi lên
              máy chủ, giám thị không thấy, không ảnh hưởng bài làm. */}
          <button
            onClick={() => onToggleFlag(q.id)}
            aria-pressed={flagged}
            title={flagged ? "Bỏ đánh dấu câu này" : "Đánh dấu để xem lại sau"}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border ${
              flagged
                ? "bg-amber-500 text-white border-amber-500"
                : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
            }`}
          >
            <Flag size={15} className={flagged ? "fill-white" : ""} />
            {flagged ? "Đã đánh dấu" : "Đánh dấu xem lại"}
          </button>
        </div>

        {/* Nội dung câu hỏi. AD-98: nếu có `blocks` (đề nạp mới) → render chữ ↔ ảnh
            ĐÚNG THỨ TỰ trong file QTI (vd: xét nghiệm → hình → câu hỏi). Đề cũ không
            có blocks → lùi về hiển thị toàn bộ chữ rồi ảnh (như trước). */}
        {/* AD-107: hiển thị BẢN NHỎ (thumb) — máy 4GB không phải giải nén tấm
            1600px cho khung ~700px; bấm phóng to mới tải bản đầy đủ (src). */}
        {q.blocks && q.blocks.length > 0 ? (
          <div className="mb-4">
            {q.blocks.map((b, i) =>
              b.type === "table" && b.rows?.length ? (
                <QuestionTable key={i} rows={b.rows} header={!!b.header} />
              ) : b.type === "image" && b.src ? (
                <img key={i} src={b.thumb || b.src} onClick={() => setZoom({ full: b.src!, thumb: b.thumb || b.src! })}
                  loading="lazy" decoding="async" title="Bấm để phóng to"
                  className="max-h-72 rounded border cursor-zoom-in hover:opacity-90 my-3" />
              ) : (
                <p key={i} className="text-slate-900 text-xl leading-relaxed font-medium whitespace-pre-wrap">{sciText(b.text || "")}</p>
              )
            )}
          </div>
        ) : (
          <>
            {/* Câu hỏi: ưu tiên — chữ to, rõ (AD-69; nâng cỡ AD-125) */}
            <p className="text-slate-900 text-xl leading-relaxed font-medium mb-4 whitespace-pre-wrap">{sciText(q.text)}</p>
            {q.images && q.images.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-5">
                {q.images.map((src, i) => (
                  <img key={i} src={q.thumbs?.[i] || src} onClick={() => setZoom({ full: src, thumb: q.thumbs?.[i] || src })}
                    loading="lazy" decoding="async"
                    title="Bấm để phóng to"
                    className="max-h-72 rounded border cursor-zoom-in hover:opacity-90" />
                ))}
              </div>
            )}
          </>
        )}

        {/* Đáp án (AD-125): trước đây cố ý thu nhỏ còn 14px để "nhường chỗ cho câu
            hỏi" — thực địa 30-07 báo chữ nhỏ khó đọc. Nay 16px, vẫn nhỏ hơn câu hỏi
            (20px) nên thứ bậc vẫn rõ, và ô bấm rộng hơn cho dễ chọn. */}
        <div className="space-y-2">
          {q.options.map((o, i) => {
            const selected = answers[q.id] === o.id;
            // Per QTI: the displayed label is POSITIONAL (A,B,C,D top to bottom).
            // Shuffle reorders the option content; the letters never travel. We
            // still submit/score by the option's stable identifier (o.id).
            const label = String.fromCharCode(65 + i);
            return (
              <button key={o.id} onClick={() => onSelect(q.id, o.id)}
                className={`w-full text-left flex items-start gap-3 border rounded-lg px-3.5 py-2.5 text-base leading-relaxed transition ${selected ? "border-blue-600 bg-blue-50" : "border-slate-200 hover:bg-slate-50"}`}>
                <span className={`w-7 h-7 shrink-0 rounded-full flex items-center justify-center text-sm font-bold ${selected ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-600"}`}>{label}</span>
                <span className="flex-1 whitespace-pre-wrap">{sciText(o.text)}</span>
                {o.images && o.images.length > 0 && (
                  <span className="flex flex-wrap gap-1 shrink-0">
                    {o.images.map((src, i) => (
                      <img key={i} src={o.thumbs?.[i] || src}
                        loading="lazy" decoding="async"
                        onClick={(e) => { e.stopPropagation(); setZoom({ full: src, thumb: o.thumbs?.[i] || src }); }}
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

      {/* Xem ảnh phóng to: nhiều mức, kéo chuột để xem vùng cần, có nút Đóng (AD-135). */}
      {zoom && (
        <ImageLightbox full={zoom.full} thumb={zoom.thumb} onClose={() => setZoom(null)} />
      )}
    </div>
  );
}

/** Bảng trong đề (AD-129). Ô chỉ chứa CHỮ (bộ nạp đã bóc sẵn) nên không có đường
 * nhúng HTML từ file đề. Cuộn ngang riêng để bảng rộng không đẩy vỡ layout câu hỏi. */
function QuestionTable({ rows, header }: { rows: string[][]; header: boolean }) {
  const body = header ? rows.slice(1) : rows;
  return (
    <div className="my-3 overflow-x-auto">
      <table className="border-collapse text-base">
        {header && (
          <thead>
            <tr>
              {rows[0].map((c, i) => (
                <th key={i} className="border border-slate-400 px-3 py-1.5 bg-slate-100 font-semibold text-left align-top">
                  {sciText(c)}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {body.map((r, ri) => (
            <tr key={ri}>
              {r.map((c, ci) => (
                <td key={ci} className="border border-slate-400 px-3 py-1.5 align-top">{sciText(c)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default memo(QuestionCard);
