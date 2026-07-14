import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, CheckCircle2, Clock, FileQuestion, Pencil, Plus, Trash2 } from "lucide-react";
import type { Exam, Sitting } from "../../api/types";
import { sittingsApi, type SittingCreate } from "../../api/sittings";
import { errorMessage } from "../../api/client";
import StatusBadge from "../../components/StatusBadge";
import Modal from "../../components/Modal";
import Field from "../../components/Field";

interface Ctx { examId: string; exam: Exam }

export default function SittingsTab() {
  const { examId, exam } = useOutletContext<Ctx>();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<Sitting | null>(null);
  const empty: SittingCreate = { name: "", description: "", scheduled_date: null, duration_minutes: exam.duration_minutes };
  const [form, setForm] = useState<SittingCreate>(empty);
  const [msg, setMsg] = useState("");

  const { data: sittings = [], isLoading } = useQuery({
    queryKey: ["sittings", examId], queryFn: () => sittingsApi.list(examId), enabled: !!examId,
  });
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["sittings", examId] });
    qc.invalidateQueries({ queryKey: ["exam", examId] });
  };
  const createMut = useMutation({
    mutationFn: () => sittingsApi.create(examId, form),
    onSuccess: () => { setCreateOpen(false); setForm(empty); invalidate(); },
    onError: (e) => setMsg(errorMessage(e)),
  });
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-slate-800">Buổi thi</h2>
        <button onClick={() => { setMsg(""); setForm(empty); setCreateOpen(true); }}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700">
          <Plus size={16} /> Tạo buổi thi
        </button>
      </div>
      <p className="text-sm text-slate-500">
        Mỗi buổi thi mang một bộ đề (QTI) riêng. Tất cả thí sinh dự mọi buổi.
      </p>

      {msg && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 px-3 py-2 rounded">{msg}</p>}

      <div className="bg-white rounded-xl shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2">Buổi thi</th>
              <th className="px-4 py-2">Trạng thái</th>
              <th className="px-4 py-2">Đề thi</th>
              <th className="px-4 py-2">Thời lượng</th>
              <th className="px-4 py-2">Ngày</th>
              <th className="px-4 py-2 text-right">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && <tr><td colSpan={6} className="px-4 py-6 text-center text-slate-400">Đang tải…</td></tr>}
            {!isLoading && sittings.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">Chưa có buổi thi. Bấm <strong>Tạo buổi thi</strong>.</td></tr>
            )}
            {sittings.map((s) => (
              <tr key={s.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link to={`/exams/${examId}/sittings/${s.id}`} className="text-blue-600 hover:underline font-medium">
                    {s.name}
                  </Link>
                  {s.description && <p className="text-xs text-slate-500 mt-0.5">{s.description}</p>}
                </td>
                <td className="px-4 py-3"><StatusBadge status={s.status} hasRunningSessions={s.has_running_sessions} /></td>
                <td className="px-4 py-3 text-slate-600">
                  {s.has_payload
                    ? <span className="inline-flex items-center gap-1 text-green-700"><CheckCircle2 size={14} /> {s.question_count} câu</span>
                    : s.status === "closed"
                      ? <span className="inline-flex items-center gap-1 text-slate-500" title="Đề đã bị xoá khi đóng buổi (bảo mật)"><Trash2 size={14} /> Đã xoá đề{s.question_count > 0 ? ` (${s.question_count} câu)` : ""}</span>
                      : <span className="inline-flex items-center gap-1 text-amber-600"><FileQuestion size={14} /> Chưa nạp đề</span>}
                </td>
                <td className="px-4 py-3 text-slate-600"><span className="inline-flex items-center gap-1"><Clock size={13} />{s.duration_minutes}'</span></td>
                <td className="px-4 py-3 text-slate-600">
                  {s.scheduled_date ? <span className="inline-flex items-center gap-1"><CalendarDays size={13} />{s.scheduled_date}</span> : "—"}
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <Link to={`/exams/${examId}/sittings/${s.id}`} className="text-xs text-blue-600 hover:underline mr-3">Mở →</Link>
                  {s.status === "draft" && (
                    <button title="Sửa buổi thi" onClick={() => setEditing(s)}
                      className="p-1 rounded hover:bg-slate-100 align-middle">
                      <Pencil size={15} className="text-slate-500" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal open={createOpen} title="Tạo buổi thi mới" onClose={() => { setCreateOpen(false); setForm(empty); }}>
        <div className="space-y-3">
          <Field label="Tên buổi thi *">
            <input className="input" value={form.name} autoFocus placeholder="VD: Buổi 1 — Lý thuyết"
              onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Mô tả (tuỳ chọn)">
            <textarea className="input" rows={2} value={form.description ?? ""}
              onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Thời lượng (phút) *">
              <input type="number" min={1} max={600} className="input" value={form.duration_minutes}
                onChange={(e) => setForm({ ...form, duration_minutes: Number(e.target.value) || 45 })} />
            </Field>
            <Field label="Ngày thi (tuỳ chọn)">
              <input type="date" className="input" value={form.scheduled_date ?? ""}
                onChange={(e) => setForm({ ...form, scheduled_date: e.target.value || null })} />
            </Field>
          </div>
          {createMut.isError && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">{errorMessage(createMut.error)}</p>}
          <button onClick={() => createMut.mutate()} disabled={!form.name || createMut.isPending}
            className="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 disabled:opacity-60">
            {createMut.isPending ? "Đang tạo…" : "Tạo buổi thi"}
          </button>
          <p className="text-xs text-slate-500 text-center">Sau khi tạo, vào buổi thi để nạp đề (QTI) rồi mở buổi.</p>
        </div>
      </Modal>

      {editing && (
        <EditSittingModal sitting={editing} onClose={() => setEditing(null)}
          onSaved={() => { setEditing(null); invalidate(); }} />
      )}
    </div>
  );
}

function EditSittingModal({ sitting, onClose, onSaved }: {
  sitting: Sitting; onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState({
    name: sitting.name,
    scheduled_date: sitting.scheduled_date,
    duration_minutes: sitting.duration_minutes,
  });
  const save = useMutation({
    mutationFn: () => sittingsApi.update(sitting.id, form),
    onSuccess: onSaved,
  });
  return (
    <Modal open title="Sửa buổi thi" onClose={onClose}>
      <div className="space-y-3">
        <Field label="Tên buổi thi *">
          <input className="input" value={form.name} autoFocus
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Thời lượng (phút) *">
            <input type="number" min={1} max={600} className="input" value={form.duration_minutes}
              onChange={(e) => setForm({ ...form, duration_minutes: Number(e.target.value) || 45 })} />
          </Field>
          <Field label="Ngày thi (tuỳ chọn)">
            <input type="date" className="input" value={form.scheduled_date ?? ""}
              onChange={(e) => setForm({ ...form, scheduled_date: e.target.value || null })} />
          </Field>
        </div>
        {save.isError && <p className="text-sm text-rose-700">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border text-sm">Huỷ</button>
          <button onClick={() => save.mutate()} disabled={!form.name.trim() || save.isPending}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm disabled:opacity-50">
            {save.isPending ? "Đang lưu…" : "Lưu"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
