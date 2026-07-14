import { useRef, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileArchive, Loader2, Upload, X } from "lucide-react";
import { sittingsApi } from "../../api/sittings";
import { errorMessage } from "../../api/client";
import type { Sitting } from "../../api/types";

interface Ctx { examId: string; sittingId: string; sitting: Sitting }
type Phase = "idle" | "uploading" | "done";

export default function SectionExamTab() {
  const { examId, sittingId, sitting } = useOutletContext<Ctx>();
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [code, setCode] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");

  const hasExam = sitting.has_payload;
  // Block upload only when candidates are actively taking THIS buổi.
  const isRunning = sitting.status === "active" && sitting.has_running_sessions;

  const importMut = useMutation({
    mutationFn: async () => {
      setPhase("uploading"); setProgress(0); setError("");
      return sittingsApi.importQti(sittingId, file!, code, (p) => setProgress(p));
    },
    onSuccess: () => {
      setPhase("done");
      qc.invalidateQueries({ queryKey: ["sitting", sittingId] });
      qc.invalidateQueries({ queryKey: ["sittings", examId] });
      qc.invalidateQueries({ queryKey: ["exam", examId] });
    },
    onError: (e) => { setError(errorMessage(e)); setPhase("idle"); },
  });

  function fmtSize(n: number): string {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  }
  function pickFile(f: File | null) {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".qenc")) {
      setError("File phải là .qenc — mã hoá đề bằng phần mềm Mã hoá đề thi trước khi nạp."); return;
    }
    setFile(f); setError(""); setPhase("idle");
  }
  function clear() {
    setFile(null); setCode(""); setPhase("idle"); setProgress(0); setError("");
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <div className="max-w-3xl">
      {hasExam && phase !== "done" && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-4 mb-4">
          <div className="flex items-center gap-3">
            <CheckCircle2 size={24} className="text-green-600" />
            <div className="flex-1">
              <p className="font-semibold text-slate-800">
                Đề đã nạp ({sitting.question_count} câu · {sitting.duration_minutes} phút)
              </p>
              <p className="text-xs text-slate-600">
                {isRunning
                  ? "Thí sinh đang làm bài. Hãy Đóng buổi trước nếu muốn nạp đề khác."
                  : "Sẵn sàng. Mở buổi rồi vào tab Giám sát để bắt đầu thi, hoặc nạp đề khác bên dưới để thay thế."}
              </p>
            </div>
          </div>
        </div>
      )}

      {phase === "done" ? (
        <div className="bg-green-50 border border-green-200 rounded-xl p-6 text-center">
          <CheckCircle2 size={48} className="mx-auto text-green-500 mb-2" />
          <h3 className="text-lg font-bold text-slate-800">Đã nạp đề thành công</h3>
          <p className="text-sm text-slate-600 mt-1">{sitting.question_count} câu hỏi · sẵn sàng cho thí sinh.</p>
          <button onClick={clear} className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
            Đóng
          </button>
        </div>
      ) : (
        <div className="bg-white rounded-xl shadow-sm p-5 space-y-4">
          <h3 className="font-semibold text-slate-800">
            {hasExam ? "Nạp đề khác (thay thế đề hiện tại)" : "Nạp đề thi cho buổi thi này"}
          </h3>

          {isRunning && (
            <p className="text-sm bg-amber-50 text-amber-800 border border-amber-200 rounded p-2">
              ⚠️ Thí sinh đang làm bài. Bấm <strong>Đóng buổi</strong> trước khi nạp đề khác.
            </p>
          )}

          {file ? (
            <div className="bg-green-50 border-2 border-green-300 rounded-lg p-4 flex items-center gap-3">
              <div className="bg-green-500 text-white rounded-full p-2 shrink-0">
                <CheckCircle2 size={22} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-slate-800 truncate">{file.name}</p>
                <p className="text-xs text-slate-500">{fmtSize(file.size)} · sẵn sàng để nạp</p>
              </div>
              {phase !== "uploading" && (
                <button onClick={clear} className="text-slate-400 hover:text-rose-600 p-1" title="Chọn file khác">
                  <X size={18} />
                </button>
              )}
            </div>
          ) : (
            <label
              className={`block border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition ${
                isRunning ? "border-slate-200 bg-slate-50 opacity-60 pointer-events-none"
                : "border-slate-300 hover:border-blue-400 hover:bg-slate-50"
              }`}
            >
              <FileArchive size={40} className="mx-auto text-slate-400 mb-2" />
              <p className="text-sm text-slate-700 font-medium">Bấm để chọn file đề <code>.qenc</code> (đã mã hoá bằng phần mềm Mã hoá đề thi)</p>
              <input ref={fileRef} type="file" accept=".qenc" className="hidden"
                onChange={(e) => pickFile(e.target.files?.[0] ?? null)} disabled={isRunning} />
            </label>
          )}

          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">
              Mã kích hoạt (8 số)
            </label>
            <input inputMode="numeric" value={code} maxLength={8}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
              disabled={phase === "uploading" || isRunning}
              className="input font-mono tracking-widest" placeholder="12345678" />
            <p className="text-[11px] text-slate-500 mt-1">
              Xem trên phần mềm <b>Mã hoá đề thi</b> (máy người ra đề) — mã đổi mỗi 30 phút.
            </p>
          </div>

          {phase === "uploading" && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
              <div className="flex items-center gap-2 text-sm text-blue-700 font-medium mb-2">
                <Loader2 size={16} className="animate-spin" />
                {progress < 100 ? `Đang tải lên… ${progress}%` : "Đang giải nén & phân tích QTI…"}
              </div>
              <div className="h-2 bg-blue-100 rounded overflow-hidden">
                <div className="h-full bg-blue-600 transition-all" style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}
          {error && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">{error}</p>}

          <button
            onClick={() => importMut.mutate()}
            disabled={!file || code.length !== 8 || phase === "uploading" || isRunning}
            className="w-full px-5 py-2.5 rounded-lg bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2 font-medium"
          >
            {phase === "uploading" ? (
              <><Loader2 size={16} className="animate-spin" /> Đang nạp đề…</>
            ) : (
              <><Upload size={16} /> Nạp đề thi</>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
