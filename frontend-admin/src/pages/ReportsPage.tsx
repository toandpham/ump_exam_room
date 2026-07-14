import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileDown, Lock, ShieldCheck } from "lucide-react";
import { sittingsApi } from "../api/sittings";
import { errorMessage } from "../api/client";
import type { Sitting } from "../api/types";
import Modal from "../components/Modal";

interface Ctx { examId: string; sittingId: string; sitting: Sitting }

export default function ReportsPage() {
  const { sittingId } = useOutletContext<Ctx>();
  const [pwOpen, setPwOpen] = useState(false);
  const { data: report, isLoading } = useQuery({
    queryKey: ["report", sittingId],
    queryFn: () => sittingsApi.report(sittingId),
    enabled: !!sittingId,
  });

  const [integ, setInteg] = useState<{ ok: boolean; text: string } | null>(null);
  const [checking, setChecking] = useState(false);
  async function runIntegrity() {
    setChecking(true); setInteg(null);
    try {
      const r = await sittingsApi.integrity(sittingId);
      const bad = r.mismatched.length;
      const legacy = r.unsealed_legacy.length ? ` (${r.unsealed_legacy.length} bài cũ chưa niêm phong)` : "";
      if (r.checked === 0) setInteg({ ok: true, text: "Chưa có bài nào đã nộp để kiểm tra." });
      else if (bad === 0) setInteg({ ok: true, text: `✓ ${r.ok}/${r.checked} bài NGUYÊN VẸN — không phát hiện can thiệp.${legacy}` });
      else setInteg({ ok: false, text: `⚠ PHÁT HIỆN ${bad}/${r.checked} bài bị CAN THIỆP sau khi nộp! Cần điều tra ngay.` });
    } catch (e) {
      setInteg({ ok: false, text: errorMessage(e, "Kiểm tra thất bại.") });
    } finally {
      setChecking(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-800">Báo cáo kết quả</h2>
        <div className="flex gap-2">
          <button onClick={() => setPwOpen(true)} className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-white text-sm hover:bg-slate-50">
            <FileDown size={16} /> Excel
          </button>
          <button onClick={runIntegrity} disabled={checking || !sittingId}
            title="Kiểm tra kết quả có bị chỉnh sửa sau khi nộp không"
            className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-white text-sm hover:bg-slate-50 disabled:opacity-50">
            <ShieldCheck size={16} /> {checking ? "Đang kiểm tra…" : "Kiểm tra toàn vẹn"}
          </button>
        </div>
      </div>

      {integ && (
        <div className={`mb-4 px-3 py-2 rounded text-sm border ${
          integ.ok ? "bg-green-50 border-green-200 text-green-800" : "bg-rose-50 border-rose-200 text-rose-800"
        }`}>
          {integ.text}
        </div>
      )}

      <ExportPasswordModal
        open={pwOpen} onClose={() => setPwOpen(false)}
        onConfirm={async (pw) => {
          await sittingsApi.reportXlsx(sittingId, pw || undefined);
          setPwOpen(false);
        }}
      />

      {isLoading && <p className="text-slate-400">Đang tải…</p>}
      {report && (() => {
        const rows = report.rows;
        const registered = rows.length;
        const absent = rows.filter((r) => r.status === "absent").length;
        const submitted = rows.filter((r) => r.status === "submitted" || r.status === "timeout").length;
        const present = registered - absent;
        const boxes = [
          { label: "Đăng ký", value: registered, cls: "text-slate-800" },
          { label: "Vắng", value: absent, cls: "text-rose-600" },
          { label: "Dự thi", value: present, cls: "text-blue-700" },
          { label: "Đã nộp", value: submitted, cls: "text-green-700" },
        ];
        return (
          <div className="bg-white rounded-xl shadow-sm p-4">
            <h3 className="font-semibold text-slate-700 mb-3 text-sm">Thống kê</h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {boxes.map((b) => (
                <div key={b.label} className="rounded-lg border border-slate-200 p-4 text-center">
                  <div className={`text-3xl font-bold ${b.cls}`}>{b.value}</div>
                  <div className="text-sm text-slate-500 mt-1">{b.label}</div>
                </div>
              ))}
            </div>
            <p className="text-sm text-slate-600 mt-3">
              Đã nộp <strong>{submitted}</strong>/<strong>{present}</strong> bài
              {present === 0
                ? <span className="text-slate-400"> — chưa có thí sinh dự thi</span>
                : submitted >= present
                ? <span className="font-medium text-green-700"> — ✓ đã thu đủ bài</span>
                : <span className="font-medium text-amber-600"> — còn {present - submitted} bài chưa nộp</span>}
            </p>
          </div>
        );
      })()}
    </div>
  );
}

function ExportPasswordModal({
  open, onClose, onConfirm,
}: { open: boolean; onClose: () => void; onConfirm: (pw: string) => Promise<void> }) {
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function go(usePassword: boolean) {
    setBusy(true); setErr("");
    try {
      await onConfirm(usePassword ? pw : "");
      setPw("");
    } catch (e) {
      setErr(errorMessage(e));
    } finally { setBusy(false); }
  }

  return (
    <Modal open={open} title="Xuất file Excel kết quả" onClose={() => { setPw(""); setErr(""); onClose(); }}>
      <div className="space-y-3">
        <p className="text-sm text-slate-600">
          Nhập mật khẩu để xuất file <strong>ZIP mã hoá AES-256</strong> chứa Excel kết quả
          (kèm cột đáp án từng câu của thí sinh).
        </p>
        <div className="relative">
          <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="password" value={pw} onChange={(e) => setPw(e.target.value)}
            placeholder="Mật khẩu (≥6 ký tự)"
            className="input pl-9" autoFocus
          />
        </div>
        {err && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">{err}</p>}
        <div className="flex justify-end gap-2 pt-2 border-t">
          <button onClick={() => go(false)} disabled={busy}
            className="px-3 py-2 text-sm rounded-lg border hover:bg-slate-50 disabled:opacity-50">
            Tải không mã hoá
          </button>
          <button onClick={() => go(true)} disabled={busy || pw.length < 6}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
            {busy ? "Đang xuất…" : "Xuất ZIP mã hoá"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
