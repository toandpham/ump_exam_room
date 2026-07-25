import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Clock, FileQuestion, Lock, Plus, Shield, Trash2 } from "lucide-react";
import { examsApi, type SectionCreate } from "../api/exams";
import { errorMessage } from "../api/client";
import { useExamsList } from "../hooks/useExamsList";
import { useAuthStore } from "../stores/auth";
import Modal from "../components/Modal";
import StatusBadge from "../components/StatusBadge";
import { CreateWizard } from "./exams/CreateWizard";

const EMPTY: SectionCreate = {
  name: "",
  description: "",
  duration_minutes: 45,
  exam_date: null,
  allow_registration: false,
  room_count: 1,
  room_capacity: 0,
  sittings: [{ name: "Buổi 1", scheduled_date: null, duration_minutes: null }],
};

export default function ExamsPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  // Role split (AD-25): giám thị (proctor) create + operate sections; quản trị
  // (super_admin) can only view + delete — no create, no entering the section.
  const isSuper = useAuthStore((s) => s.admin?.role) === "super_admin";
  const { data: exams = [], isLoading } = useExamsList();

  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState<SectionCreate>(EMPTY);
  const [msg, setMsg] = useState("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["exams"] });

  const createMut = useMutation({
    mutationFn: () => examsApi.create(form),
    onSuccess: (exam) => {
      setCreateOpen(false);
      setForm(EMPTY);
      invalidate();
      navigate(`/exams/${exam.id}/candidates`);
    },
    onError: (e) => setMsg(errorMessage(e)),
  });
  const deleteMut = useMutation({
    mutationFn: (id: string) => examsApi.remove(id),
    onSuccess: invalidate,
    onError: (e) => setMsg(errorMessage(e)),
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Kỳ thi</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {isSuper
              ? "Quản trị chỉ xem và xoá kỳ thi. Việc tổ chức thi do giám thị thực hiện."
              : "Mỗi kỳ thi là 1 lần tổ chức độc lập — có danh sách thí sinh, đề thi, giám sát và báo cáo riêng."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {!isSuper && (
            <button
              onClick={() => { setMsg(""); setCreateOpen(true); }}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700"
            >
              <Plus size={16} /> Tạo kỳ thi
            </button>
          )}
        </div>
      </div>

      {msg && <p className="mb-3 text-sm text-rose-700 bg-rose-50 border border-rose-200 px-3 py-2 rounded">{msg}</p>}

      <div className="bg-white rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2 font-medium">Tên kỳ thi</th>
              <th className="px-4 py-2 font-medium">Trạng thái</th>
              <th className="px-4 py-2 font-medium">Chủ tịch hội đồng</th>
              <th className="px-4 py-2 font-medium">Buổi thi</th>
              <th className="px-4 py-2 font-medium">Thời lượng</th>
              <th className="px-4 py-2 font-medium">Ngày thi</th>
              <th className="px-4 py-2 font-medium text-right">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && (
              <tr><td colSpan={7} className="px-4 py-6 text-center text-slate-400">Đang tải…</td></tr>
            )}
            {!isLoading && exams.length === 0 && (
              <tr><td colSpan={7} className="px-4 py-10 text-center text-slate-400">
                {isSuper
                  ? "Chưa có kỳ thi nào trong hệ thống."
                  : <>Chưa có kỳ thi. Bấm <strong>Tạo kỳ thi</strong> để bắt đầu.</>}
              </td></tr>
            )}
            {exams.map((ex) => (
              <tr key={ex.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  {isSuper ? (
                    <span className="font-medium text-slate-800">{ex.name}</span>
                  ) : (
                    <Link to={`/exams/${ex.id}`} className="text-blue-600 hover:underline font-medium">
                      {ex.name}
                    </Link>
                  )}
                  {ex.description && <p className="text-xs text-slate-500 mt-0.5">{ex.description}</p>}
                </td>
                <td className="px-4 py-3"><StatusBadge status={ex.status} hasRunningSessions={ex.has_running_sessions} /></td>
                <td className="px-4 py-3 text-slate-600">
                  {ex.created_by_name
                    ? <span className="inline-flex items-center gap-1"><Shield size={13} className="text-slate-400" />{ex.created_by_name}</span>
                    : <span className="text-slate-400 italic">— (chung)</span>}
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {ex.sitting_count > 0
                    ? <span className="flex items-center gap-1"><FileQuestion size={13} />{ex.sitting_count} buổi</span>
                    : <span className="text-amber-600">Chưa có buổi</span>}
                </td>
                <td className="px-4 py-3 text-slate-600">
                  <span className="flex items-center gap-1"><Clock size={13} />{ex.duration_minutes}'</span>
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {ex.exam_date
                    ? <span className="flex items-center gap-1"><CalendarDays size={13} />{ex.exam_date}</span>
                    : "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1">
                    {isSuper ? (
                      <button
                        title={ex.status === "active" ? "Đang chạy — không xoá được" : "Xoá kỳ thi"}
                        disabled={ex.status === "active"}
                        onClick={() => confirm(`Xoá kỳ thi "${ex.name}"? Tất cả thí sinh + kết quả sẽ mất.`) && deleteMut.mutate(ex.id)}
                        className="p-1.5 rounded hover:bg-slate-100 disabled:cursor-not-allowed"
                      >
                        {ex.status === "active"
                          ? <Lock size={16} className="text-slate-300" />
                          : <Trash2 size={16} className="text-red-600" />}
                      </button>
                    ) : (
                      <Link to={`/exams/${ex.id}`} className="text-xs text-blue-600 hover:underline">Mở →</Link>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal open={createOpen} title="Tạo kỳ thi mới — thiết lập ban đầu" onClose={() => { setCreateOpen(false); setForm(EMPTY); }}>
        <CreateWizard
          form={form} setForm={setForm}
          onSubmit={() => createMut.mutate()}
          submitting={createMut.isPending}
          error={createMut.isError ? errorMessage(createMut.error) : ""}
        />
      </Modal>
    </div>
  );
}
