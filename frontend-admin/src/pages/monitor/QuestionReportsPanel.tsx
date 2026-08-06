import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, ChevronDown, ChevronRight } from "lucide-react";
import { monitorApi } from "../../api/monitor";
import { errorMessage } from "../../api/client";

/** Khiếu nại câu hỏi do thí sinh gửi trong lúc làm bài.
 *
 * Đặt ngay trên bảng giám sát vì hội đồng cần biết NGAY khi có người báo "câu 47
 * thiếu hình" — chờ tới lúc chấm mới đọc thì đã muộn. Thu gọn khi không có gì mới
 * để không chiếm chỗ.
 *
 * Còn xem được sau khi đóng buổi: đó là lúc hội đồng chấm, mà lúc đó đề đã bị xoá. */
export default function QuestionReportsPanel({ sittingId }: { sittingId: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(true);
  const [err, setErr] = useState("");

  const { data: reports = [] } = useQuery({
    queryKey: ["question-reports", sittingId],
    queryFn: () => monitorApi.questionReports(sittingId),
    enabled: !!sittingId,
    refetchInterval: 15000,
  });

  const resolve = useMutation({
    mutationFn: ({ id, resolution }: { id: string; resolution: string }) =>
      monitorApi.resolveQuestionReport(id, resolution),
    onSuccess: () => {
      setErr("");
      qc.invalidateQueries({ queryKey: ["question-reports", sittingId] });
      qc.invalidateQueries({ queryKey: ["sessions", sittingId] });
    },
    onError: (e) => setErr(errorMessage(e, "Không lưu được kết luận")),
  });

  if (reports.length === 0) return null;
  const pending = reports.filter((r) => !r.resolved_at);

  return (
    <div className="mb-3 rounded-xl border-2 border-orange-300 bg-orange-50">
      <button onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left font-bold text-orange-900">
        {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        <AlertTriangle size={18} />
        {pending.length > 0
          ? `${pending.length} khiếu nại về câu hỏi chưa xử lý`
          : `${reports.length} khiếu nại về câu hỏi — đã xử lý hết`}
      </button>

      {open && (
        <div className="px-3 pb-3">
          {err && <p className="mb-2 text-sm text-rose-700">{err}</p>}
          <ul className="space-y-1.5">
            {reports.map((r) => (
              <li key={r.id}
                className={`rounded-lg border px-3 py-2 text-sm ${
                  r.resolved_at ? "bg-white/60 border-slate-200 text-slate-500"
                                : "bg-white border-orange-200"}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-slate-800">
                      Câu {r.question_number}
                      <span className="font-normal text-slate-500">
                        {" · "}{r.full_name} · {r.cccd}
                        {r.room_name ? ` · ${r.room_name}` : ""}
                      </span>
                    </p>
                    <p className="text-slate-700 whitespace-pre-wrap break-words">{r.content}</p>
                    {r.resolved_at && (
                      <p className="mt-1 text-xs text-green-700">
                        ✓ {r.resolution}
                        {r.resolved_by_name ? ` — ${r.resolved_by_name}` : ""}
                      </p>
                    )}
                  </div>
                  {!r.resolved_at && (
                    <button
                      onClick={() => {
                        const resolution = prompt(
                          `Kết luận của hội đồng cho câu ${r.question_number}:`, "");
                        if (resolution === null) return;
                        if (resolution.trim().length < 3) {
                          setErr("Hãy ghi kết luận (ít nhất 3 ký tự).");
                          return;
                        }
                        resolve.mutate({ id: r.id, resolution: resolution.trim() });
                      }}
                      className="shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded border border-green-300 bg-green-50 hover:bg-green-100 text-xs text-green-700">
                      <Check size={14} /> Đã xử lý
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
