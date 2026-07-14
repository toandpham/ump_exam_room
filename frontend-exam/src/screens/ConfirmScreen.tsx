import { useState } from "react";
import { CheckCircle2, Flag } from "lucide-react";
import { examApi } from "../api/exam";
import { errorMessage } from "../api/client";
import { photoUrl, useStore } from "../store";

export default function ConfirmScreen({ onConfirmed }: { onConfirmed: () => void }) {
  const { candidate, exam, logout } = useStore();
  const [disputed, setDisputed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!candidate || !exam) return null;

  async function confirm() {
    setBusy(true);
    setError(null);
    try {
      await examApi.confirm();
      onConfirmed();
    } catch (e) {
      setError(errorMessage(e, "Không thể xác nhận. Vui lòng thử lại hoặc báo giám thị."));
    } finally {
      setBusy(false);
    }
  }
  async function dispute() {
    setError(null);
    try {
      await examApi.dispute();
      setDisputed(true);
    } catch (e) {
      setError(errorMessage(e, "Không gửi được báo giám thị. Vui lòng thử lại."));
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-lg bg-white rounded-2xl shadow-lg p-8">
        <h1 className="text-xl font-bold text-slate-800 text-center mb-1">Xác nhận thông tin</h1>
        <p className="text-center text-slate-500 mb-5">Kỳ thi: <strong>{exam.name}</strong></p>
        <div className="flex gap-5">
          {candidate.photo_path && (
            <img
              src={photoUrl(candidate.photo_path)}
              className="w-44 h-56 object-cover rounded-lg border bg-slate-100 shrink-0"
              onError={(e) => (e.currentTarget.style.visibility = "hidden")}
            />
          )}
          <dl className="flex-1 text-sm space-y-1">
            <Row k="Họ tên" v={candidate.full_name} />
            <Row k="Ngày sinh" v={candidate.birth_date} />
            <Row k="Đơn vị" v={candidate.unit} />
            <Row k="Ngành" v={candidate.major || "—"} />
            <Row k="Đối tượng" v={candidate.category} />
            <Row k="Lần dự thi" v={String(candidate.attempt_number)} />
            <Row k={candidate.id_type === "passport" ? "Hộ chiếu" : "CCCD"} v={candidate.cccd} />
          </dl>
        </div>

        {error && (
          <p className="mt-6 text-center text-rose-700 bg-rose-50 border border-rose-200 rounded-lg py-3 px-3 text-sm">
            {error}
          </p>
        )}
        {disputed ? (
          <div className="mt-6 text-center text-amber-700 bg-amber-50 rounded-lg py-3 px-3 space-y-2">
            <p>Đã báo giám thị. Vui lòng chờ giám thị sửa thông tin.</p>
            <p className="text-sm">Sau khi giám thị báo đã sửa xong, bấm nút dưới để tải lại thông tin mới.</p>
            <button onClick={logout}
              className="mt-1 px-4 py-2 rounded-lg bg-amber-600 text-white text-sm hover:bg-amber-700">
              Đăng nhập lại để xem thông tin đã sửa
            </button>
          </div>
        ) : (
          <div className="mt-6 flex gap-3">
            <button onClick={dispute} className="flex-1 flex items-center justify-center gap-2 border border-slate-300 rounded-lg py-3 hover:bg-slate-50">
              <Flag size={18} /> Báo giám thị
            </button>
            <button onClick={confirm} disabled={busy} className="flex-1 flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 text-white rounded-lg py-3 disabled:opacity-60">
              <CheckCircle2 size={18} /> {busy ? "Đang xác nhận…" : "Đúng thông tin"}
            </button>
          </div>
        )}
        <button onClick={logout} className="mt-4 w-full text-xs text-slate-400 hover:text-slate-600">Đăng xuất</button>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex">
      <dt className="w-28 text-slate-500">{k}</dt>
      <dd className="font-medium text-slate-800">{v}</dd>
    </div>
  );
}
