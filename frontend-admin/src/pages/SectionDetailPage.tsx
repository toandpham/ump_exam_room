import { useParams } from "react-router-dom";
import { NavLink, Outlet, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, DoorClosed, FileText, LayoutGrid, Monitor, Power, Users } from "lucide-react";
import { examsApi } from "../api/exams";
import { errorMessage } from "../api/client";
import StatusBadge from "../components/StatusBadge";

const TABS = [
  { to: "overview",   label: "Tổng quan", icon: LayoutGrid, end: false },
  { to: "candidates", label: "Thí sinh",  icon: Users,      end: false },
  { to: "rooms",      label: "Phòng & giám thị", icon: DoorClosed, end: false },
  { to: "sittings",   label: "Buổi thi",  icon: FileText,   end: false },
];

export default function SectionDetailPage() {
  const qc = useQueryClient();
  const { examId = "" } = useParams();
  const { data: exam, isLoading } = useQuery({
    queryKey: ["exam", examId],
    queryFn: () => examsApi.get(examId),
    enabled: !!examId,
  });

  // Close = archive the exam (force-submit any running buổi + close) so a new
  // exam can be created. Per-buổi run-control lives inside the sitting detail.
  const closeMut = useMutation({
    mutationFn: () => examsApi.close(examId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["exam", examId] });
      qc.invalidateQueries({ queryKey: ["exams"] });
      // Closing force-submits + closes every running buổi server-side, so the
      // sitting/session/report caches are all stale now.
      qc.invalidateQueries({ queryKey: ["sittings", examId] });
      qc.invalidateQueries({ queryKey: ["sessions"] });
      qc.invalidateQueries({ queryKey: ["report"] });
    },
  });

  const kioskQuitMut = useMutation({
    mutationFn: () => examsApi.kioskQuit(examId),
    onSuccess: () => alert("Đã gửi lệnh thoát. Các máy thi sẽ tự đóng trong ~5 giây."),
    onError: (e) => alert(errorMessage(e, "Gửi lệnh thoát máy thi thất bại")),
  });

  if (isLoading) return <p className="text-slate-400">Đang tải kỳ thi…</p>;
  if (!exam) return <p className="text-rose-600">Không tìm thấy kỳ thi.</p>;

  return (
    <div>
      <Link to="/exams" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 mb-2">
        <ArrowLeft size={16} /> Tất cả kỳ thi
      </Link>

      <div className="bg-white rounded-xl shadow-sm p-4 mb-4">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-bold text-slate-800">{exam.name}</h1>
              <StatusBadge status={exam.status} hasRunningSessions={exam.has_running_sessions} />
              {exam.status === "active" && (
                <button
                  onClick={() => {
                    if (confirm(
                      "Đóng kỳ thi này (lưu trữ)?\n\nMọi buổi thi đang chạy sẽ được tự nộp + chấm. Kỳ thi sẽ đóng và không thao tác được nữa (kết quả + báo cáo vẫn giữ). Chỉ đóng được khi không còn buổi nào đang mở.",
                    )) closeMut.mutate();
                  }}
                  disabled={closeMut.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600 text-white text-sm font-semibold hover:bg-rose-700 disabled:opacity-60"
                >
                  <Power size={15} /> {closeMut.isPending ? "Đang đóng…" : "Đóng kỳ thi (lưu trữ)"}
                </button>
              )}
              {exam.status === "active" && (
                <button
                  onClick={() => {
                    if (confirm(
                      "Thoát tất cả máy thi?\n\nLệnh đóng sẽ gửi tới mọi máy thi của kỳ thi này (các máy tự đóng trong khoảng 5 giây). Dùng khi đã kết thúc thi.",
                    )) kioskQuitMut.mutate();
                  }}
                  disabled={kioskQuitMut.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600 text-white text-sm font-semibold hover:bg-amber-700 disabled:opacity-60"
                >
                  <Monitor size={15} /> {kioskQuitMut.isPending ? "Đang gửi…" : "Thoát máy thi"}
                </button>
              )}
            </div>
            {exam.description && <p className="text-sm text-slate-500 mt-1">{exam.description}</p>}
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500 mt-2">
              {exam.exam_date && <span>📅 {exam.exam_date}</span>}
              <span>⏱ {exam.duration_minutes} phút</span>
              <span>📚 {exam.sitting_count} buổi thi</span>
              {exam.question_count > 0 && <span>📄 {exam.question_count} câu (tổng)</span>}
            </div>
            {closeMut.isError && (
              <p className="mt-2 text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">
                {errorMessage(closeMut.error)}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Tab navigation */}
      <div className="border-b border-slate-200 mb-4">
        <nav className="flex gap-1">
          {TABS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
                  isActive
                    ? "border-blue-600 text-blue-700"
                    : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
                }`
              }
            >
              <Icon size={15} /> {label}
            </NavLink>
          ))}
        </nav>
      </div>

      <Outlet context={{ examId, exam }} />
    </div>
  );
}
