import { useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, UserPlus } from "lucide-react";
import { examApi, type ActiveExamSummary } from "../api/exam";
import { errorMessage } from "../api/client";
import { useStore } from "../store";
import IdentityInput, { type IdType, ID_ERROR, validateId } from "../components/IdentityInput";

export default function RegisterScreen({ onBack }: { onBack: () => void }) {
  const login = useStore((s) => s.login);

  // At most one section is active at a time (auto-active on creation). We just
  // look it up and confirm "you're signing up for X".
  const [section, setSection] = useState<ActiveExamSummary | null>(null);
  const [sectionError, setSectionError] = useState("");
  const [sectionLoading, setSectionLoading] = useState(true);

  const [idType, setIdType] = useState<IdType>("cccd");
  const [cccd, setCccd] = useState("");
  const [fullName, setFullName] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [unit, setUnit] = useState("");
  const [category, setCategory] = useState("Đối tượng 1");
  const [attemptNumber, setAttemptNumber] = useState(1);
  const [graduationYear, setGraduationYear] = useState("");
  const [major, setMajor] = useState("");

  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    examApi.activeExams()
      .then((list) => {
        if (list.length === 0) setSectionError("Hiện chưa có kỳ thi nào đang mở. Vui lòng liên hệ giám thị.");
        else setSection(list[0]);
      })
      .catch((e) => setSectionError(errorMessage(e, "Không tải được thông tin kỳ thi.")))
      .finally(() => setSectionLoading(false));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!section) return setError("Hiện chưa có kỳ thi nào đang mở.");
    if (!validateId(idType, cccd)) return setError(ID_ERROR[idType]);
    if (!fullName.trim()) return setError("Vui lòng nhập họ tên.");
    if (!birthDate) return setError("Vui lòng chọn ngày sinh.");
    if (!unit.trim()) return setError("Vui lòng nhập đơn vị.");
    if (!category.trim()) return setError("Vui lòng nhập đối tượng.");

    setSubmitting(true);
    try {
      const res = await examApi.register({
        cccd, full_name: fullName.trim(), birth_date: birthDate, unit: unit.trim(),
        category: category.trim(), attempt_number: attemptNumber,
        graduation_year: graduationYear ? Number(graduationYear) : null,
        major: major.trim() || null,
      });
      if (res.token) login(res.token, res.candidate, res.exam);
    } catch (err) {
      setError(errorMessage(err, "Đăng ký thất bại. Vui lòng thử lại."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4 py-6">
      <form onSubmit={submit} className="w-full max-w-xl bg-white rounded-2xl shadow-lg p-7 space-y-3">
        <div className="flex items-center gap-3">
          <button type="button" onClick={onBack} className="text-slate-400 hover:text-slate-700">
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-xl font-bold text-slate-800">Đăng ký dự thi</h1>
            <p className="text-xs text-slate-500">Khai báo trung thực — thông tin sẽ được giám thị đối chiếu giấy tờ.</p>
          </div>
        </div>

        {sectionLoading ? (
          <p className="text-sm text-slate-500">Đang tải thông tin kỳ thi…</p>
        ) : sectionError ? (
          <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">{sectionError}</p>
        ) : section ? (
          <div className="bg-blue-50 border border-blue-200 rounded p-3">
            <div className="flex items-center gap-2 text-blue-800">
              <CheckCircle2 size={16} /> <strong>{section.name}</strong>
            </div>
            <p className="text-xs mt-0.5 ml-6 text-blue-700">
              {section.exam_date ? `${section.exam_date} · ` : ""}{section.duration_minutes} phút
            </p>
          </div>
        ) : null}

        <fieldset disabled={!section} className="contents">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Giấy tờ tuỳ thân *">
              <IdentityInput
                variant="register"
                idType={idType}
                value={cccd}
                onIdTypeChange={(t) => { setIdType(t); setCccd(""); }}
                onValueChange={setCccd}
              />
            </Field>
            <Field label="Họ tên *">
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} className="input" />
            </Field>
            <Field label="Ngày sinh *">
              <input type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)} className="input" />
            </Field>
            <Field label="Đơn vị *">
              <input value={unit} onChange={(e) => setUnit(e.target.value)} className="input" />
            </Field>
            <Field label="Đối tượng *">
              <input value={category} onChange={(e) => setCategory(e.target.value)} className="input" />
            </Field>
            <Field label="Lần dự thi">
              <input type="number" min={1} max={99} value={attemptNumber}
                onChange={(e) => setAttemptNumber(Number(e.target.value) || 1)} className="input" />
            </Field>
            <Field label="Ngành (tuỳ chọn)">
              <input value={major} onChange={(e) => setMajor(e.target.value)} className="input" />
            </Field>
            <Field label="Năm tốt nghiệp (tuỳ chọn)">
              <input type="number" min={1900} max={2100} value={graduationYear}
                onChange={(e) => setGraduationYear(e.target.value)} className="input" />
            </Field>
          </div>
        </fieldset>

        {error && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">{error}</p>}

        <button
          type="submit"
          disabled={submitting || !section}
          className="w-full flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 disabled:opacity-60 text-white font-medium py-3 rounded-lg"
        >
          <UserPlus size={18} />
          {submitting ? "Đang đăng ký…" : "Đăng ký và vào thi"}
        </button>
      </form>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-slate-600 mb-1">{label}</span>
      {children}
    </label>
  );
}
