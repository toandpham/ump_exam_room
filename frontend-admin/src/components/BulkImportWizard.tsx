import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Download, FileSpreadsheet, Image as ImageIcon } from "lucide-react";
import { candidatesApi, type ImportPreview, type ZipReport } from "../api/candidates";
import { errorMessage } from "../api/client";
import { useExamsList } from "../hooks/useExamsList";
import Modal from "./Modal";

export default function BulkImportWizard({ open, onClose, lockedExamId }: {
  open: boolean; onClose: () => void; lockedExamId?: string;
}) {
  const qc = useQueryClient();
  // Skip the exam list query when locked — we already know which section.
  const { data: exams = [] } = useExamsList(!lockedExamId);
  const [step, setStep] = useState(1);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [examId, setExamId] = useState(lockedExamId ?? "");
  const [commitResult, setCommitResult] = useState<{ created: number; updated?: number; skipped: number } | null>(null);
  const [zipReport, setZipReport] = useState<ZipReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const excelRef = useRef<HTMLInputElement>(null);
  const zipRef = useRef<HTMLInputElement>(null);

  function reset() {
    setStep(1); setPreview(null); setExamId(lockedExamId ?? ""); setCommitResult(null);
    setZipReport(null); setErr(""); onClose();
  }

  async function run<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true); setErr("");
    try { return await fn(); }
    catch (e) { setErr(errorMessage(e)); }
    finally { setBusy(false); }
  }

  return (
    <Modal open={open} title="Nhập danh sách thí sinh" onClose={reset} width="max-w-3xl">
      <ol className="flex gap-2 text-xs mb-4">
        {["Template", "Tải lên + kiểm tra", "Xác nhận", "Ảnh (ZIP)", "Hoàn tất"].map((s, i) => (
          <li key={s} className={`px-2 py-1 rounded ${step === i + 1 ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-500"}`}>
            {i + 1}. {s}
          </li>
        ))}
      </ol>

      {step === 1 && (
        <div className="space-y-3 text-sm">
          <p>Tải file mẫu Excel, điền danh sách thí sinh (cột: CCCD, Họ tên, Ngày sinh, Đơn vị, Năm TN, Ngành, Đối tượng, Lần dự thi, Phòng). Cột <strong>Phòng</strong> (tuỳ chọn) tự chia thí sinh vào phòng — tên phòng mới sẽ được tạo tự động.</p>
          <button onClick={() => candidatesApi.downloadTemplate()} className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-white hover:bg-slate-50">
            <Download size={16} /> Tải template Excel
          </button>
          <input ref={excelRef} type="file" accept=".xlsx" className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0]; e.target.value = "";
              if (!file) return;
              const p = await run(() => candidatesApi.importPreview(file));
              if (p) { setPreview(p); setStep(2); }
            }} />
          <button onClick={() => excelRef.current?.click()} disabled={busy}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700">
            <FileSpreadsheet size={16} /> Tải lên file đã điền
          </button>
          {err && <p className="text-red-600">{err}</p>}
        </div>
      )}

      {step === 2 && preview && (
        <div className="space-y-3 text-sm">
          <p>Tổng {preview.total_rows} dòng · <span className="text-green-700">{preview.valid_count} hợp lệ</span> · <span className="text-red-600">{preview.error_count} lỗi</span></p>
          {/* Dòng lỗi KHÔNG được nhập — phải đập vào mắt. Danh sách 400+ dòng khiến
              vài dòng lỗi lọt thỏm ở giữa bảng (sự cố 22-07: 420 → 400 mà không ai
              để ý). Nên: banner đỏ + đẩy dòng lỗi lên ĐẦU bảng. */}
          {preview.error_count > 0 && (
            <p className="bg-red-50 border border-red-300 text-red-800 rounded p-2 font-semibold">
              ⚠️ {preview.error_count} dòng sẽ KHÔNG được nhập (xem lý do ở đầu bảng).
              Chỉ {preview.valid_count}/{preview.total_rows} thí sinh được tạo.
              Sửa file rồi tải lên lại nếu cần đủ danh sách.
            </p>
          )}
          <div className="max-h-72 overflow-auto border rounded">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 sticky top-0"><tr>
                <th className="px-2 py-1 text-left">Dòng</th><th className="px-2 py-1 text-left">CCCD / Hộ chiếu</th>
                <th className="px-2 py-1 text-left">Họ tên</th><th className="px-2 py-1 text-left">Lỗi</th>
              </tr></thead>
              <tbody>
                {[...preview.rows].sort((a, b) => Number(a.valid) - Number(b.valid)).map((r) => (
                  <tr key={r.row_number} className={r.valid ? "" : "bg-red-50"}>
                    <td className="px-2 py-1">{r.row_number}</td>
                    <td className="px-2 py-1 font-mono">
                      {String(r.data.cccd ?? "")}
                      {r.data.id_type === "passport" && (
                        <span className="ml-1 px-1 rounded bg-amber-100 text-amber-700 text-[10px] font-sans">HC</span>
                      )}
                    </td>
                    <td className="px-2 py-1">{String(r.data.full_name ?? "")}</td>
                    <td className="px-2 py-1 text-red-600">{r.errors.join("; ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button disabled={preview.valid_count === 0} onClick={() => setStep(3)}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60">
            Tiếp tục ({preview.valid_count} hợp lệ)
          </button>
        </div>
      )}

      {step === 3 && preview && (
        <div className="space-y-3 text-sm">
          {lockedExamId ? (
            <p className="bg-blue-50 text-blue-700 border border-blue-200 rounded p-2">
              {preview.valid_count} thí sinh hợp lệ sẽ được gán <strong>vào kỳ thi hiện tại</strong>.
            </p>
          ) : (
            <>
              <p>Gán {preview.valid_count} thí sinh hợp lệ vào kỳ thi (tuỳ chọn):</p>
              <select className="input" value={examId} onChange={(e) => setExamId(e.target.value)}>
                <option value="">— Không gán ngay —</option>
                {exams.filter((e) => e.status !== "active").map((ex) => <option key={ex.id} value={ex.id}>{ex.name}</option>)}
              </select>
            </>
          )}
          {err && <p className="text-red-600">{err}</p>}
          <button disabled={busy} onClick={async () => {
            const res = await run(() => candidatesApi.importCommit(preview.token, examId || null));
            if (res) {
              setCommitResult(res);
              qc.invalidateQueries({ queryKey: ["candidates"] });
              qc.invalidateQueries({ queryKey: ["candidate-stats"] });
              qc.invalidateQueries({ queryKey: ["roster"] });
              // The Excel "Phòng" column may have created/changed room splits.
              qc.invalidateQueries({ queryKey: ["rooms"] });
              setStep(4);
            }
          }} className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-60">
            {busy ? "Đang tạo…" : "Xác nhận tạo tài khoản"}
          </button>
        </div>
      )}

      {step === 4 && (
        <div className="space-y-3 text-sm">
          {commitResult && (
            <p className="text-green-700">
              ✓ Tạo {commitResult.created} mới
              {commitResult.updated ? `, chuyển ${commitResult.updated} thí sinh sẵn có sang kỳ này` : ""}
              {commitResult.skipped ? `, bỏ qua ${commitResult.skipped}` : ""}.
            </p>
          )}
          <p>Tải lên ảnh thí sinh (file ZIP, tên file = CCCD, vd <code>079200000001.jpg</code>):</p>
          <input ref={zipRef} type="file" accept=".zip" className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0]; e.target.value = "";
              if (!file) return;
              const rep = await run(() => candidatesApi.uploadZip(file));
              if (rep) { setZipReport(rep); qc.invalidateQueries({ queryKey: ["candidates"] }); }
            }} />
          <button onClick={() => zipRef.current?.click()} disabled={busy}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-white hover:bg-slate-50">
            <ImageIcon size={16} /> Tải lên ZIP ảnh
          </button>
          {zipReport && (
            <div className="bg-slate-50 p-3 rounded">
              <p className="text-green-700">Cập nhật {zipReport.updated} ảnh.</p>
              {zipReport.unmatched_files.length > 0 && <p className="text-amber-700">Không khớp: {zipReport.unmatched_files.join(", ")}</p>}
              {zipReport.invalid_files.length > 0 && <p className="text-red-600">Lỗi: {zipReport.invalid_files.join(", ")}</p>}
            </div>
          )}
          {err && <p className="text-red-600">{err}</p>}
          <button onClick={reset} className="px-4 py-2 rounded-lg bg-slate-700 text-white hover:bg-slate-800">Hoàn tất</button>
        </div>
      )}
    </Modal>
  );
}
