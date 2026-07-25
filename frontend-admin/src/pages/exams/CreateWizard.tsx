/** Wizard tạo kỳ thi: tên/ngày/thời lượng + số phòng + builder buổi thi (AD-48).
 * Tách khỏi ExamsPage ở refactor đợt 3 — thuần props, không tự gọi API.
 * NumberInput ở cuối file: ô số gõ tự do, xoá trống được, clamp khi rời ô. */
import { useEffect, useRef, useState } from "react";
import { DoorClosed, Plus, X } from "lucide-react";
import type { SectionCreate } from "../../api/exams";
import Field from "../../components/Field";

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
