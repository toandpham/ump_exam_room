import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Clock, DoorClosed, FileQuestion, Lock, Plus, Shield, Trash2, X } from "lucide-react";
import { examsApi, type SectionCreate } from "../api/exams";
import { errorMessage } from "../api/client";
import { useExamsList } from "../hooks/useExamsList";
import { useAuthStore } from "../stores/auth";
import Modal from "../components/Modal";
import Field from "../components/Field";
import StatusBadge from "../components/StatusBadge";

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

export function CreateWizard({ form, setForm, onSubmit, submitting, error }: {
  form: SectionCreate;
  setForm: (f: SectionCreate) => void;
  onSubmit: () => void;
  submitting: boolean;
  error: string;
}) {
  const sittings = form.sittings ?? [];
  const setSittings = (next: NonNullable<SectionCreate["sittings"]>) => setForm({ ...form, sittings: next });
  const addSitting = () =>
    setSittings([...sittings, { name: `Buổi ${sittings.length + 1}`, scheduled_date: null, duration_minutes: null }]);
  const patchSitting = (i: number, patch: Partial<NonNullable<SectionCreate["sittings"]>[number]>) =>
    setSittings(sittings.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));
  const removeSitting = (i: number) => setSittings(sittings.filter((_, idx) => idx !== i));

  const valid = !!form.name.trim() && sittings.length > 0 && sittings.every((s) => s.name.trim());

  return (
    <div className="space-y-4">
      <Field label="Tên kỳ thi *">
        <input className="input" value={form.name} placeholder="VD: Kỳ thi thử quốc gia lần 1"
          onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Thời lượng làm bài mặc định (phút) *">
          <NumberInput className="input" min={1} max={600} fallback={45}
            value={form.duration_minutes}
            onChange={(n) => setForm({ ...form, duration_minutes: n })} />
        </Field>
        <Field label="Số phòng thi *">
          <div className="relative">
            <DoorClosed size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <NumberInput className="input pl-8" min={1} max={50} fallback={1}
              value={form.room_count ?? 1}
              onChange={(n) => setForm({ ...form, room_count: n })} />
          </div>
        </Field>
      </div>
      <Field label="Sức chứa mỗi phòng (tối đa thí sinh)">
        <NumberInput className="input" min={0} max={500} fallback={0}
          placeholder="VD: 30 — để 0 nếu không giới hạn"
          value={form.room_capacity ?? 0}
          onChange={(n) => setForm({ ...form, room_capacity: n })} />
      </Field>
      <p className="-mt-2 text-xs text-slate-400">Hệ thống tạo sẵn "Phòng 1…N"; gán giám thị + đổi tên/sức chứa ở tab Phòng thi sau.</p>

      {/* Buổi thi builder */}
      <div className="rounded-lg border border-slate-200 p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-slate-600">Buổi thi * (mỗi buổi nạp 1 đề riêng, dùng chung danh sách thí sinh)</span>
          <button type="button" onClick={addSitting}
            className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline">
            <Plus size={13} /> Thêm buổi
          </button>
        </div>
        <div className="space-y-2">
          {sittings.map((s, i) => (
            <div key={i} className="flex items-center gap-2">
              <input className="input flex-1" placeholder={`Tên buổi ${i + 1} (VD: Sáng 03/06)`}
                value={s.name} onChange={(e) => patchSitting(i, { name: e.target.value })} />
              <input type="date" className="input w-36" value={s.scheduled_date ?? ""}
                onChange={(e) => patchSitting(i, { scheduled_date: e.target.value || null })} />
              <input type="number" min={1} max={600} className="input w-20" title="Thời lượng (phút) — để trống = mặc định"
                placeholder={`${form.duration_minutes}'`} value={s.duration_minutes ?? ""}
                onChange={(e) => patchSitting(i, { duration_minutes: e.target.value ? Number(e.target.value) : null })} />
              <button type="button" title="Xoá buổi" disabled={sittings.length <= 1}
                onClick={() => removeSitting(i)}
                className="p-1.5 rounded hover:bg-slate-100 disabled:opacity-30">
                <X size={15} className="text-slate-500" />
              </button>
            </div>
          ))}
        </div>
      </div>

      <label className="flex items-start gap-2 cursor-pointer rounded-lg border border-slate-200 p-3 hover:bg-slate-50">
        <input type="checkbox" className="mt-0.5" checked={form.allow_registration ?? false}
          onChange={(e) => setForm({ ...form, allow_registration: e.target.checked })} />
        <span className="text-sm">
          <span className="font-medium text-slate-800">Cho phép thí sinh đăng ký tại chỗ</span>
          <span className="block text-xs text-slate-500">
            Bật: thí sinh chưa có trong danh sách có thể tự khai báo + vào thi. Tắt (mặc định): chỉ thí sinh đã import mới vào được.
          </span>
        </span>
      </label>

      {error && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">{error}</p>}
      <button onClick={onSubmit} disabled={!valid || submitting}
        className="w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 disabled:opacity-60">
        {submitting ? "Đang tạo…" : `Tạo kỳ thi (${form.room_count ?? 1} phòng · ${sittings.length} buổi)`}
      </button>
      <p className="text-xs text-slate-500 text-center">
        Sau khi tạo: vào tab <strong>Thí sinh</strong> import danh sách → tab <strong>Phòng thi</strong> gán giám thị + xếp chỗ → mỗi <strong>Buổi thi</strong> nạp đề (QTI) rồi mở buổi.
      </p>
    </div>
  );
}

/** A number input you can actually type in: it keeps its own text state so the
 *  field can be emptied (no "0"/"1" stuck at the front), and only normalizes —
 *  clamp to [min,max], fall back when blank — when you leave the field (blur). */
function NumberInput({ value, onChange, min, max, fallback, className, placeholder }: {
  value: number;
  onChange: (n: number) => void;
  min: number;
  max?: number;
  fallback: number;     // value used when the field is left blank
  className?: string;
  placeholder?: string;
}) {
  const [text, setText] = useState(value ? String(value) : "");
  // Re-sync when the form value changes from outside (e.g. reset after submit).
  const emitted = useRef(value);
  useEffect(() => {
    if (value !== emitted.current) {
      setText(value ? String(value) : "");
      emitted.current = value;
    }
  }, [value]);

  return (
    <input
      type="number" inputMode="numeric" min={min} max={max}
      className={className} placeholder={placeholder} value={text}
      onChange={(e) => {
        const raw = e.target.value;
        setText(raw);                       // keep exactly what was typed
        if (raw !== "") {
          const n = Number(raw);
          if (!Number.isNaN(n)) { emitted.current = n; onChange(n); }
        }
      }}
      onBlur={() => {
        let n = text === "" ? fallback : Number(text);
        if (Number.isNaN(n)) n = fallback;
        n = Math.max(min, max != null ? Math.min(max, n) : n);
        emitted.current = n;
        onChange(n);
        setText(n ? String(n) : "");        // show the normalized value (blank for 0)
      }}
    />
  );
}
