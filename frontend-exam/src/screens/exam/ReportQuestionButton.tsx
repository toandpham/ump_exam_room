import { useState } from "react";
import { AlertTriangle, Check, X } from "lucide-react";

/** Nút "Báo lỗi câu hỏi" + hộp nhập nội dung.
 *
 * Vì sao cần: thí sinh gặp "câu 47 thiếu hình" thì giơ tay, giám thị ghi ra giấy,
 * đến lúc hội đồng chấm thì thất lạc. Nút "Báo giám thị" sẵn có chỉ dùng cho SAI
 * THÔNG TIN CÁ NHÂN và không mang được nội dung. Ở đây nội dung được lưu cùng bài
 * thi, gắn đúng số câu, hội đồng đọc lúc chấm.
 *
 * Cố ý KHÔNG chặn làm bài: gửi xong đóng hộp, thí sinh làm tiếp. Lỗi gửi thì báo
 * ngay tại chỗ để em ấy biết mà gọi giám thị. */
export default function ReportQuestionButton({ questionNumber, onSend }: {
  questionNumber: number;
  onSend: (content: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [err, setErr] = useState("");

  const close = () => { setOpen(false); setText(""); setState("idle"); setErr(""); };

  const send = async () => {
    const content = text.trim();
    if (content.length < 3) { setErr("Hãy mô tả ngắn gọn vấn đề của câu này."); return; }
    setState("sending"); setErr("");
    try {
      await onSend(content);
      setState("sent");
      setTimeout(close, 1800);
    } catch (e: any) {
      setState("error");
      setErr(e?.message || "Không gửi được. Hãy báo trực tiếp giám thị.");
    }
  };

  return (
    <>
      <button onClick={() => setOpen(true)}
        title="Báo cho hội đồng biết câu này có vấn đề (thiếu hình, sai đề…)"
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border bg-white text-slate-600 border-slate-300 hover:bg-slate-50">
        <AlertTriangle size={15} /> Báo lỗi câu hỏi
      </button>

      {open && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
          role="dialog" aria-label="Báo lỗi câu hỏi">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-5">
            <div className="flex items-start justify-between gap-3 mb-2">
              <h3 className="text-lg font-bold text-slate-800">
                Báo lỗi câu {questionNumber}
              </h3>
              <button onClick={close} aria-label="Đóng"
                className="text-slate-400 hover:text-slate-700"><X size={20} /></button>
            </div>

            {state === "sent" ? (
              <p className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded p-3">
                <Check size={18} /> Đã gửi tới hội đồng. Em cứ làm bài tiếp bình thường.
              </p>
            ) : (
              <>
                <p className="text-sm text-slate-500 mb-2">
                  Mô tả ngắn gọn vấn đề — ví dụ "thiếu hình", "không có đáp án đúng",
                  "chữ bị mờ". Nội dung được lưu cùng bài thi để hội đồng xem xét.
                  Việc này <strong>không ảnh hưởng</strong> đáp án hay thời gian làm bài.
                </p>
                <textarea autoFocus value={text} onChange={(e) => setText(e.target.value)}
                  maxLength={1000} rows={4}
                  placeholder="Nội dung báo lỗi…"
                  className="w-full border border-slate-300 rounded-lg p-2.5 text-base focus:outline-none focus:ring-2 focus:ring-blue-400" />
                {err && <p className="text-sm text-rose-700 mt-1">{err}</p>}
                <div className="flex justify-end gap-2 mt-3">
                  <button onClick={close}
                    className="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50">
                    Huỷ
                  </button>
                  <button onClick={send} disabled={state === "sending"}
                    className="px-4 py-2 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700 disabled:opacity-60">
                    {state === "sending" ? "Đang gửi…" : "Gửi"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
