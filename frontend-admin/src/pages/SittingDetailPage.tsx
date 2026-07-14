import { Link, NavLink, Outlet, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BarChart3, FileText, MonitorPlay, Play, Power } from "lucide-react";
import { sittingsApi } from "../api/sittings";
import { errorMessage } from "../api/client";
import StatusBadge from "../components/StatusBadge";

const TABS = [
  { to: "exam",    label: "Đề thi",   icon: FileText,    end: false },
  { to: "monitor", label: "Giám sát", icon: MonitorPlay, end: false },
  { to: "reports", label: "Báo cáo",  icon: BarChart3,   end: false },
];

export default function SittingDetailPage() {
  const qc = useQueryClient();
  const { examId = "", sittingId = "" } = useParams();
  const { data: sitting, isLoading } = useQuery({
    queryKey: ["sitting", sittingId],
    queryFn: () => sittingsApi.get(sittingId),
    enabled: !!sittingId,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["sitting", sittingId] });
    qc.invalidateQueries({ queryKey: ["sittings", examId] });
    qc.invalidateQueries({ queryKey: ["exam", examId] });
    qc.invalidateQueries({ queryKey: ["sessions", sittingId] });
    qc.invalidateQueries({ queryKey: ["roster", sittingId] });
    // Đóng buổi force-submits the running bài → the report numbers change too.
    qc.invalidateQueries({ queryKey: ["report", sittingId] });
  };

  const openMut = useMutation({ mutationFn: () => sittingsApi.open(sittingId), onSuccess: invalidate });
  const endMut = useMutation({ mutationFn: () => sittingsApi.end(sittingId), onSuccess: invalidate });

  if (isLoading) return <p className="text-slate-400">Đang tải buổi thi…</p>;
  if (!sitting) return <p className="text-rose-600">Không tìm thấy buổi thi.</p>;

  const canOpen = sitting.status === "draft" && sitting.has_payload;
  const isActive = sitting.status === "active";

  return (
    <div>
      <Link to={`/exams/${examId}/sittings`} className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-2">
        <ArrowLeft size={16} /> Các buổi thi
      </Link>

      <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-2xl font-bold text-slate-800">{sitting.name}</h1>
          <StatusBadge status={sitting.status} hasRunningSessions={sitting.has_running_sessions} />
          {canOpen && (
            <button onClick={() => { if (confirm("Mở buổi thi này? Thí sinh sẽ có thể đăng nhập và chờ bắt đầu thi.")) openMut.mutate(); }}
              disabled={openMut.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-600 text-white text-sm font-semibold hover:bg-green-700 disabled:opacity-60">
              <Play size={15} /> {openMut.isPending ? "Đang mở…" : "Mở buổi"}
            </button>
          )}
          {isActive && (
            <button onClick={() => {
              if (confirm("Đóng buổi thi này?\n\nHệ thống sẽ tự nộp + chấm các bài đang làm, XOÁ ĐỀ khỏi server và đóng buổi (không mở lại được). Kết quả + báo cáo vẫn giữ.")) endMut.mutate();
            }}
              disabled={endMut.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600 text-white text-sm font-semibold hover:bg-rose-700 disabled:opacity-60">
              <Power size={15} /> {endMut.isPending ? "Đang đóng…" : "Đóng buổi"}
            </button>
          )}
        </div>
        {sitting.description && <p className="text-sm text-slate-500 mt-1">{sitting.description}</p>}
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500 mt-2">
          {sitting.scheduled_date && <span>📅 {sitting.scheduled_date}</span>}
          <span>⏱ {sitting.duration_minutes} phút</span>
          {sitting.has_payload
            ? <span>📄 {sitting.question_count} câu</span>
            : sitting.status === "closed"
              ? <span className="text-slate-500" title="Đề đã bị xoá khi đóng buổi (bảo mật)">🗑 Đã xoá đề{sitting.question_count > 0 ? ` (${sitting.question_count} câu)` : ""}</span>
              : <span className="text-amber-600">📄 Chưa nạp đề</span>}
        </div>
        {(openMut.isError || endMut.isError) && (
          <p className="mt-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">
            {errorMessage(openMut.error || endMut.error)}
          </p>
        )}
      </div>

      <div className="border-b border-slate-200 mb-4">
        <nav className="flex gap-1">
          {TABS.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
                  isActive ? "border-blue-600 text-blue-700"
                    : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
                }`}>
              <Icon size={15} /> {label}
            </NavLink>
          ))}
        </nav>
      </div>

      <Outlet context={{ examId, sittingId, sitting }} />
    </div>
  );
}
