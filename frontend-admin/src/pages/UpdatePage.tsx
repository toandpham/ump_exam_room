import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, DownloadCloud, Loader2, RefreshCw, XCircle } from "lucide-react";
import { systemApi } from "../api/system";
import { errorMessage } from "../api/client";

// Trang Cập nhật hệ thống (AD-89, super_admin). Bấm nút → backend ghi file yêu cầu →
// watcher trên máy chủ chạy update.sh (tự chặn khi đang thi) → trạng thái hiện ở đây.
// Trong lúc cập nhật backend bị khởi động lại → poll sẽ lỗi tạm — coi như "đang chạy".

export default function UpdatePage() {
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const [requested, setRequested] = useState(false);

  const { data: st, isError } = useQuery({
    queryKey: ["update-status"],
    queryFn: systemApi.updateStatus,
    refetchInterval: (q) => (q.state.data?.state === "running" || q.state.data?.queued ? 3000 : 10000),
    retry: false,
  });

  const req = useMutation({
    mutationFn: systemApi.requestUpdate,
    onSuccess: (r) => { setMsg(r.detail); setRequested(true); qc.invalidateQueries({ queryKey: ["update-status"] }); },
    onError: (e) => setMsg(errorMessage(e, "Không gửi được yêu cầu")),
  });

  if (requested && (st?.state === "done" || st?.state === "failed") && !st?.queued) {
    // chạy xong (thành công hay thất bại) → thôi coi lỗi-poll là đang cập nhật
    if (!isError) setTimeout(() => setRequested(false), 0);
  }
  // Backend đang restart giữa lúc cập nhật → API chết tạm thời: hiện "đang chạy".
  // requested = mình vừa bấm — backend restart làm poll lỗi tạm thời vẫn coi là đang chạy.
  const updating = st?.state === "running" || st?.queued || (isError && requested);

  return (
    <div className="max-w-2xl space-y-5">
      <h1 className="text-xl font-bold text-slate-800">Cập nhật hệ thống</h1>

      {/* Trạng thái phiên bản */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-2">
        <p className="text-sm text-slate-600">
          Bản đang chạy: <b className="font-mono">{st?.local ?? "—"}</b>
          {st?.remote && st.remote !== st.local && (
            <> · bản mới nhất: <b className="font-mono">{st.remote}</b></>
          )}
        </p>
        {st?.checked_at && (
          <p className="text-xs text-slate-400">
            Kiểm tra bản mới lúc: {new Date(st.checked_at).toLocaleString("vi-VN")}
          </p>
        )}

        {st && !st.watcher_alive && (
          <p className="text-sm bg-amber-50 border border-amber-200 text-amber-800 rounded p-2">
            ⚠️ Dịch vụ cập nhật chưa chạy trên máy chủ. Kỹ thuật chạy lại
            {" "}<code className="font-mono">sudo ./install.sh</code> một lần để bật
            (hoặc cập nhật thủ công bằng <code className="font-mono">./update.sh</code>).
          </p>
        )}

        {st?.watcher_alive && !st.update_available && !updating && st.state !== "failed" && (
          <p className="text-sm text-emerald-700 flex items-center gap-2">
            <CheckCircle2 size={16} /> Hệ thống đang ở bản mới nhất.
          </p>
        )}
      </div>

      {/* Hành động / tiến trình */}
      {updating ? (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-5">
          <p className="flex items-center gap-2 text-blue-800 font-semibold">
            <Loader2 size={18} className="animate-spin" /> Đang cập nhật…
          </p>
          <p className="text-sm text-blue-700 mt-2">
            Quá trình mất vài phút. Trang này (và toàn hệ thống) sẽ <b>gián đoạn ngắn</b> khi
            khởi động lại — cứ để nguyên, trạng thái tự cập nhật khi xong.
          </p>
        </div>
      ) : (
        <button
          onClick={() => {
            if (confirm(
              "Cập nhật hệ thống lên bản mới nhất?\n\n" +
              "- Hệ thống sẽ GIÁN ĐOẠN vài phút (build + khởi động lại).\n" +
              "- KHÔNG cập nhật khi sắp/đang tổ chức thi.\n" +
              "- Nếu đang có thí sinh thi, hệ thống sẽ tự từ chối.",
            )) { setMsg(null); req.mutate(); }
          }}
          disabled={!st?.watcher_alive || (!st?.update_available && st?.state !== "failed")}
          className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          <DownloadCloud size={18} /> Cập nhật lên bản mới
        </button>
      )}

      {msg && !updating && <p className="text-sm text-slate-600">{msg}</p>}

      {/* Kết quả lần gần nhất */}
      {st?.state === "done" && !updating && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 text-sm text-emerald-800 flex items-center gap-2">
          <CheckCircle2 size={16} /> {st.message ?? "Cập nhật xong."}
          {st.finished_at && <span className="text-emerald-600">({new Date(st.finished_at).toLocaleString("vi-VN")})</span>}
        </div>
      )}
      {st?.state === "failed" && !updating && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 space-y-2">
          <p className="text-sm text-rose-800 font-semibold flex items-center gap-2">
            <XCircle size={16} /> {st.message ?? "Cập nhật thất bại."}
          </p>
          {st.log_tail.length > 0 && (
            <pre className="text-xs bg-white border border-rose-100 rounded p-2 overflow-x-auto text-slate-700">
              {st.log_tail.join("\n")}
            </pre>
          )}
          <p className="text-xs text-rose-700 flex items-center gap-1">
            <RefreshCw size={12} /> Sửa nguyên nhân (vd: chờ hết giờ thi) rồi bấm cập nhật lại.
          </p>
        </div>
      )}
    </div>
  );
}
