import { Link, useOutletContext } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, CalendarDays, CheckCircle2, CircleDashed, Clock, DoorClosed, FileText, Users } from "lucide-react";
import type { Exam } from "../../api/types";
import { sittingsApi } from "../../api/sittings";
import { roomsApi } from "../../api/rooms";
import { candidatesApi } from "../../api/candidates";
import StatusBadge from "../../components/StatusBadge";

interface Ctx { examId: string; exam: Exam }

export default function OverviewTab() {
  const { examId, exam } = useOutletContext<Ctx>();
  const { data: sittings = [] } = useQuery({
    queryKey: ["sittings", examId], queryFn: () => sittingsApi.list(examId), enabled: !!examId,
  });
  const { data: rooms = [] } = useQuery({
    queryKey: ["rooms", examId], queryFn: () => roomsApi.listRooms(examId), enabled: !!examId,
  });
  const { data: candPage } = useQuery({
    queryKey: ["candidates", { exam_id: examId, page_size: 1 }],
    queryFn: () => candidatesApi.list({ exam_id: examId, page: 1, page_size: 1 }), enabled: !!examId,
  });
  const totalCandidates = candPage?.total ?? 0;
  const assignedToRooms = rooms.reduce((n, r) => n + r.candidate_count, 0);
  const roomsWithProctor = rooms.filter((r) => r.proctor_id).length;

  const steps = [
    { done: totalCandidates > 0, label: "Nhập danh sách thí sinh",
      detail: totalCandidates > 0 ? `${totalCandidates} thí sinh` : "Chưa import danh sách", to: "candidates" },
    { done: rooms.length > 0 && roomsWithProctor > 0, label: "Phòng thi & gán giám thị",
      detail: `${rooms.length} phòng · ${roomsWithProctor} đã gán giám thị`, to: "rooms" },
    { done: assignedToRooms > 0, label: "Chia phòng (tự động theo file Excel)",
      detail: `${assignedToRooms}/${totalCandidates} đã có phòng · gán giám thị ở tab Phòng`, to: "rooms" },
  ];
  const setupDone = steps.every((s) => s.done);

  return (
    <div className="space-y-5">
      <div className="bg-white rounded-xl shadow-sm p-4">
        <h3 className="font-semibold text-slate-700 text-sm mb-3">Các bước thiết lập kỳ thi</h3>
        <ol className="space-y-1.5">
          {steps.map((st, i) => (
            <li key={i}>
              <Link to={`/exams/${examId}/${st.to}`}
                className="group flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-slate-50">
                {st.done
                  ? <CheckCircle2 size={18} className="text-green-500 shrink-0" />
                  : <CircleDashed size={18} className="text-amber-400 shrink-0" />}
                <span className="text-sm font-medium text-slate-700 w-44 shrink-0">{i + 1}. {st.label}</span>
                <span className="text-xs text-slate-500 flex-1 truncate">{st.detail}</span>
                <ArrowRight size={15} className="text-slate-300 group-hover:text-blue-500 shrink-0" />
              </Link>
            </li>
          ))}
        </ol>
        <p className="text-xs text-slate-400 mt-2">Xong 3 bước trên là hoàn tất thiết lập. Việc nạp đề + chạy thi nằm trong từng <strong>buổi thi</strong>.</p>
        <Link to={`/exams/${examId}/sittings`}
          className={`mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium ${
            setupDone ? "bg-blue-600 text-white hover:bg-blue-700" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
          Vào quản lý buổi thi <ArrowRight size={15} />
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card icon={<FileText size={18} className="text-blue-500" />} label="Buổi thi" value={exam.sitting_count} />
        <Card icon={<DoorClosed size={18} className="text-violet-500" />} label="Phòng thi" value={rooms.length} />
        <Card icon={<Users size={18} className="text-green-500" />} label="Thí sinh (đã chia phòng)" value={`${assignedToRooms}/${totalCandidates}`} />
        <Card icon={<Clock size={18} className="text-slate-500" />} label="Thời lượng mặc định" value={`${exam.duration_minutes}'`} />
      </div>

      <div className="bg-white rounded-xl shadow-sm p-4">
        <h3 className="font-semibold text-slate-700 text-sm mb-3">Thông tin kỳ thi</h3>
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2 text-sm">
          <Row label="Tên kỳ thi" value={exam.name} />
          <Row label="Trạng thái"><StatusBadge status={exam.status} hasRunningSessions={exam.has_running_sessions} /></Row>
          <Row label="Ngày thi" value={exam.exam_date ? <span className="inline-flex items-center gap-1"><CalendarDays size={13} /> {exam.exam_date}</span> : "—"} />
          <Row label="Cho phép đăng ký tại chỗ" value={exam.allow_registration ? "Có" : "Không"} />
          {exam.description && <Row label="Mô tả" value={exam.description} />}
        </dl>
      </div>

      <div className="bg-white rounded-xl shadow-sm p-4">
        <h3 className="font-semibold text-slate-700 text-sm mb-3">Các buổi thi</h3>
        {sittings.length === 0 ? (
          <p className="text-sm text-slate-400">Chưa có buổi thi nào. Vào tab <strong>Buổi thi</strong> để tạo.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {sittings.map((s) => (
              <li key={s.id} className="flex items-center justify-between py-2">
                <span className="font-medium text-slate-800">{s.name}</span>
                <span className="flex items-center gap-3 text-slate-500">
                  <span>{s.question_count} câu · {s.duration_minutes}'</span>
                  <StatusBadge status={s.status} hasRunningSessions={s.has_running_sessions} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function Card({ icon, label, value }: { icon: React.ReactNode; label: string; value: number | string }) {
  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <div className="flex items-center justify-between text-slate-500 text-xs">
        <span>{label}</span>{icon}
      </div>
      <p className="text-2xl font-bold text-slate-800 mt-1">{value}</p>
    </div>
  );
}

function Row({ label, value, children }: { label: string; value?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="flex gap-2">
      <dt className="text-slate-500 min-w-44">{label}</dt>
      <dd className="text-slate-800 font-medium">{children ?? value}</dd>
    </div>
  );
}
