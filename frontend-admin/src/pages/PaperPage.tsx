import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { FileDown, Printer, ScanLine, Upload } from "lucide-react";
import { api, errorMessage } from "../api/client";
import { triggerDownload } from "../api/exams";
import type { Sitting } from "../api/types";

interface Ctx { examId: string; sittingId: string; sitting: Sitting }

interface SheetRead {
  page_in_file: number;
  candidate_index: number | null;
  candidate_id: string | null;
  cccd: string;
  full_name: string;
  sheet_page: number | null;
  answers: Record<string, string>;
  unsure: number[];
  error: string | null;
}

const paperApi = {
  pdf: async (sittingId: string, path: string, params = "") => {
    const res = await api.get(`/admin/sittings/${sittingId}/paper/${path}${params}`,
      { responseType: "blob" });
    const cd = res.headers["content-disposition"] || "";
    const m = /filename="([^"]+)"/.exec(cd);
    triggerDownload(res.data, m?.[1] || path);
  },
  scan: async (sittingId: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return (await api.post(`/admin/sittings/${sittingId}/paper/scan`, fd)).data as
      { total_sheets: number; sheets: SheetRead[] };
  },
  apply: async (sittingId: string, sheets: { candidate_id: string; answers: Record<string, string> }[]) =>
    (await api.post(`/admin/sittings/${sittingId}/paper/apply`, { sheets })).data,
};

/** Dự phòng giấy: in đề + phiếu trả lời, rồi quét bài về.
 *
 * Dành cho tình huống máy hỏng hàng loạt giữa buổi — đã xảy ra với 320 máy Win7.
 *
 * Bước QUÉT và bước GHI tách rời có chủ ý: máy đọc phiếu không bao giờ chắc chắn
 * 100% (giấy nhàu, tô mờ, tẩy chưa sạch), nên phải để người nhìn kết quả rồi mới
 * quyết định ghi. Ghi thẳng là biến một tờ đọc lệch thành điểm sai không ai biết. */
export default function PaperPage() {
  const { sittingId } = useOutletContext<Ctx>();
  const [scan, setScan] = useState<{ total_sheets: number; sheets: SheetRead[] } | null>(null);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  const doScan = useMutation({
    mutationFn: (file: File) => paperApi.scan(sittingId, file),
    onSuccess: (d) => { setScan(d); setErr(""); setMsg(""); },
    onError: (e) => { setScan(null); setErr(errorMessage(e, "Không đọc được file quét")); },
  });

  const doApply = useMutation({
    mutationFn: (sheets: SheetRead[]) => paperApi.apply(sittingId,
      sheets.map((s) => ({ candidate_id: s.candidate_id!, answers: s.answers }))),
    onSuccess: (d: any) => {
      setMsg(`Đã ghi ${d.applied} bài giấy.`
        + (d.skipped?.length ? ` Bỏ qua ${d.skipped.length} bài (đã có bài trên máy).` : ""));
      setScan(null);
    },
    onError: (e) => setErr(errorMessage(e, "Ghi bài giấy thất bại")),
  });

  const usable = (scan?.sheets ?? []).filter((s) => !s.error && s.candidate_id);
  const broken = (scan?.sheets ?? []).filter((s) => s.error || !s.candidate_id);

  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-800 flex items-center gap-2 mb-2">
        <Printer size={18} /> Dự phòng giấy
      </h2>
      <p className="mb-4 text-sm text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
        Dùng khi máy hỏng hàng loạt giữa buổi. In đề và phiếu trả lời, cho thí sinh
        làm trên giấy, rồi quét phiếu về đây.{" "}
        <strong>Phải in phiếu từ trang này</strong> — mã trên phiếu là thứ giúp hệ
        thống biết bài của ai.
      </p>

      <div className="flex flex-wrap gap-2 mb-5">
        <button onClick={() => paperApi.pdf(sittingId, "exam.pdf")}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm font-medium hover:bg-slate-50">
          <FileDown size={15} /> Tải đề bản giấy
        </button>
        <button onClick={() => {
          if (confirm("Bản này CÓ ĐÁP ÁN, chỉ dành cho hội đồng.\n\nTuyệt đối không phát cho thí sinh. Vẫn tải?")) {
            paperApi.pdf(sittingId, "exam.pdf", "?with_answers=true");
          }
        }}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-amber-300 bg-amber-50 text-sm font-medium text-amber-800 hover:bg-amber-100">
          <FileDown size={15} /> Đề kèm đáp án (hội đồng)
        </button>
        <button onClick={() => paperApi.pdf(sittingId, "sheets.pdf")}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700">
          <Printer size={15} /> In phiếu trả lời
        </button>
        <label className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 bg-white text-sm font-medium hover:bg-slate-50 cursor-pointer">
          <Upload size={15} /> {doScan.isPending ? "Đang đọc…" : "Tải bản quét lên"}
          <input type="file" accept="image/*,application/pdf" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) doScan.mutate(f); e.target.value = ""; }} />
        </label>
      </div>

      {msg && <p className="mb-3 text-green-800 bg-green-50 border border-green-200 rounded p-3">{msg}</p>}
      {err && <p className="mb-3 text-rose-700 bg-rose-50 border border-rose-200 rounded p-3">{err}</p>}

      {scan && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-slate-800 flex items-center gap-2">
              <ScanLine size={16} /> Đọc được {usable.length}/{scan.total_sheets} tờ
            </h3>
            <button disabled={usable.length === 0 || doApply.isPending}
              onClick={() => {
                if (confirm(`Ghi ${usable.length} bài giấy vào hệ thống và chấm?\n\n`
                  + "Thí sinh đã có bài làm trên máy sẽ được BỎ QUA (bài trên máy luôn được ưu tiên).")) {
                  doApply.mutate(usable);
                }
              }}
              className="px-3 py-1.5 rounded-lg bg-green-600 text-white text-sm font-semibold hover:bg-green-700 disabled:opacity-50">
              {doApply.isPending ? "Đang ghi…" : `Ghi ${usable.length} bài vào hệ thống`}
            </button>
          </div>

          {broken.length > 0 && (
            <div className="mb-3 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-800">
              <strong>{broken.length} tờ không dùng được</strong> — cần nhập tay hoặc quét lại:
              <ul className="mt-1 list-disc list-inside">
                {broken.map((s) => (
                  <li key={s.page_in_file}>Trang {s.page_in_file}: {s.error}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="bg-white rounded-xl shadow-sm overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-left">
                <tr>
                  <th className="px-3 py-2">Trang</th>
                  <th className="px-3 py-2">Thí sinh</th>
                  <th className="px-3 py-2">Tờ</th>
                  <th className="px-3 py-2 text-center">Số câu đọc được</th>
                  <th className="px-3 py-2">Cần xem lại</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {usable.map((s) => (
                  <tr key={s.page_in_file} className="hover:bg-slate-50">
                    <td className="px-3 py-2 text-slate-400">{s.page_in_file}</td>
                    <td className="px-3 py-2">
                      {s.full_name}
                      <span className="block font-mono text-xs text-slate-400">{s.cccd}</span>
                    </td>
                    <td className="px-3 py-2 text-slate-600">{(s.sheet_page ?? 0) + 1}</td>
                    <td className="px-3 py-2 text-center font-semibold">
                      {Object.keys(s.answers).length}
                    </td>
                    <td className="px-3 py-2">
                      {s.unsure.length === 0
                        ? <span className="text-slate-400">—</span>
                        : <span className="text-amber-700">
                            câu {s.unsure.map((q) => q + 1).join(", ")}
                          </span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
