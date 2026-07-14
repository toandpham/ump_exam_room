import { LogOut, Pause, Play, UserCheck } from "lucide-react";
import type { RosterCandidate, SessionSummary } from "../../api/monitor";
import { STATUS_LABEL, type DisplayRow } from "./constants";

/** Bảng thí sinh hợp nhất: dòng đã đăng nhập (có phiên, kèm thao tác) và dòng
 * chưa đăng nhập (roster). Cột STT đánh số 1-based theo thứ tự dòng. */
export default function SessionTable({ rows, onLogout, onAdmit, onPause, onResume, hasRunning }: {
  rows: DisplayRow[];
  onLogout: (s: SessionSummary) => void;
  onAdmit: (s: SessionSummary) => void;
  onPause?: (s: SessionSummary) => void;
  onResume?: (s: SessionSummary) => void;
  /** true khi đã có ít nhất 1 phiên in_progress — dùng để bật nút Duyệt vào thi
   * cho thí sinh ready đi trễ xác nhận sau khi buổi đã bắt đầu. */
  hasRunning?: boolean;
}) {
  return (
    <div className="bg-white rounded-xl shadow-sm overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-slate-500 text-left">
          <tr>
            <th className="px-3 py-2 w-12 text-center">STT</th>
            <th className="px-3 py-2">Họ tên</th><th className="px-3 py-2">CCCD</th>
            <th className="px-3 py-2">Phòng</th>
            <th className="px-3 py-2">Trạng thái</th>
            <th className="px-3 py-2"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rows.map((r, i) => r.kind === "session" ? (
            <Row key={r.s.session_id} stt={i + 1} s={r.s}
              onLogout={() => onLogout(r.s)} onAdmit={() => onAdmit(r.s)}
              onPause={onPause ? () => onPause(r.s) : undefined}
              onResume={onResume ? () => onResume(r.s) : undefined}
              hasRunning={hasRunning} />
          ) : (
            <PendingRow key={r.c.candidate_id} stt={i + 1} c={r.c} />
          ))}
          {rows.length === 0 && <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-400">Không có thí sinh nào.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function PendingRow({ stt, c }: { stt: number; c: RosterCandidate }) {
  return (
    <tr className="hover:bg-slate-50 text-slate-500">
      <td className="px-3 py-2 text-center text-slate-400">{stt}</td>
      <td className="px-3 py-2 text-slate-800">{c.full_name}</td>
      <td className="px-3 py-2 font-mono text-xs">{c.cccd}</td>
      <td className="px-3 py-2">{c.room_name || "—"}</td>
      <td className="px-3 py-2 italic">Chưa đăng nhập</td>
      <td className="px-3 py-2"></td>
    </tr>
  );
}

function Row({ stt, s, onLogout, onAdmit, onPause, onResume, hasRunning }: {
  stt: number;
  s: SessionSummary;
  onLogout: () => void; onAdmit: () => void;
  onPause?: () => void; onResume?: () => void;
  hasRunning?: boolean;
}) {
  const isAbsent = s.status === "absent";
  // "Duyệt vào thi": luôn bật cho thí sinh "waiting" (đi trễ chưa phân bổ).
  // Với "ready": bật CHỈ KHI buổi đang chạy (hasRunning=true) — thí sinh xác nhận sau
  // khi "Bắt đầu thi" đã bấm; khi chưa bắt đầu thì cả phòng vào cùng lúc → mờ đi.
  const canAdmit = s.status === "waiting" || (s.status === "ready" && !!hasRunning);
  const showAdmit = s.status === "waiting" || s.status === "ready";
  return (
    <tr className={isAbsent ? "bg-slate-50" : "hover:bg-slate-50"}>
      <td className="px-3 py-2 text-center text-slate-400">{stt}</td>
      <td className="px-3 py-2">
        <span className={isAbsent ? "text-slate-400" : ""}>{s.full_name}</span>
        {isAbsent && <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-slate-200 text-slate-500">Vắng</span>}
        {s.paused && <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">tạm dừng</span>}
      </td>
      <td className="px-3 py-2 font-mono text-xs">{s.cccd}</td>
      <td className="px-3 py-2 text-slate-600">{s.room_name || "—"}</td>
      <td className="px-3 py-2">{STATUS_LABEL[s.status] || s.status}</td>
      <td className="px-3 py-2 text-right whitespace-nowrap">
        {showAdmit && (
          <button disabled={!canAdmit} onClick={canAdmit ? onAdmit : undefined}
            title={canAdmit ? "Duyệt thí sinh đi trễ vào thi ngay" : "Thí sinh đã sẵn sàng — sẽ vào thi khi bấm 'Bắt đầu thi'"}
            className={`inline-flex items-center gap-1 px-2 py-1 mr-2 rounded border text-xs ${
              canAdmit
                ? "border-green-300 bg-green-50 hover:bg-green-100 text-green-700"
                : "border-slate-200 bg-slate-50 text-slate-300 cursor-not-allowed"
            }`}>
            <UserCheck size={14} /> Duyệt vào thi
          </button>
        )}
        {s.status === "in_progress" && (onPause || onResume) && (
          s.paused ? (
            onResume && (
              <button title="Tiếp tục bài thi của thí sinh này" onClick={onResume}
                className="inline-flex items-center gap-1 px-2 py-1 mr-2 rounded border border-green-300 bg-green-50 hover:bg-green-100 text-xs text-green-700">
                <Play size={14} /> Tiếp tục
              </button>
            )
          ) : (
            onPause && (
              <button title="Tạm dừng bài thi của thí sinh này" onClick={onPause}
                className="inline-flex items-center gap-1 px-2 py-1 mr-2 rounded border border-amber-300 bg-amber-50 hover:bg-amber-100 text-xs text-amber-700">
                <Pause size={14} /> Tạm dừng
              </button>
            )
          )
        )}
        {!isAbsent && (
          <button title="Đăng xuất khỏi thiết bị (để đổi máy)" onClick={onLogout}
            className="inline-flex items-center gap-1 px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 text-xs text-slate-600">
            <LogOut size={14} /> Đăng xuất
          </button>
        )}
      </td>
    </tr>
  );
}
