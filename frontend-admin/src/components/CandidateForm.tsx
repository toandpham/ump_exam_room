import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { candidatesApi, type CandidateInput } from "../api/candidates";
import { errorMessage } from "../api/client";
import { useExamsList } from "../hooks/useExamsList";
import type { Candidate } from "../api/types";
import Modal from "./Modal";

interface Props {
  open: boolean;
  candidate: Candidate | null;
  emergency?: boolean;
  onClose: () => void;
}

export default function CandidateForm({ open, candidate, emergency, onClose }: Props) {
  const qc = useQueryClient();
  const { data: exams = [] } = useExamsList();
  const [f, setF] = useState<CandidateInput>({
    cccd: candidate?.cccd ?? "",
    full_name: candidate?.full_name ?? "",
    birth_date: candidate?.birth_date ?? "",
    unit: candidate?.unit ?? "",
    graduation_year: candidate?.graduation_year ?? null,
    major: candidate?.major ?? "",
    category: candidate?.category ?? "",
    attempt_number: candidate?.attempt_number ?? 1,
    exam_id: candidate?.exam_id ?? null,
  });
  const [idType, setIdType] = useState<"cccd" | "passport">(
    candidate?.id_type === "passport" ? "passport" : "cccd"
  );
  const [reason, setReason] = useState("");
  const [err, setErr] = useState("");

  const save = useMutation({
    mutationFn: () => {
      if (emergency) return candidatesApi.emergencyAdd({ ...f, reason });
      if (candidate) return candidatesApi.update(candidate.id, f);
      return candidatesApi.create(f);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["candidates"] });
      qc.invalidateQueries({ queryKey: ["candidate-stats"] });
      onClose();
    },
    onError: (e) => setErr(errorMessage(e)),
  });

  const title = emergency ? "Bổ sung khẩn cấp (super admin)" : candidate ? "Sửa thí sinh" : "Thêm thí sinh";

  return (
    <Modal open={open} title={title} onClose={onClose} width="max-w-xl">
      <div className="grid grid-cols-2 gap-3">
        <F label="Giấy tờ tuỳ thân">
          <div className="flex gap-1.5 mb-1.5">
            {([["cccd", "CCCD"], ["passport", "Hộ chiếu"]] as const).map(([t, l]) => (
              <button key={t} type="button" onClick={() => { setIdType(t); setF({ ...f, cccd: "" }); }}
                className={`flex-1 py-1 rounded text-xs font-medium border ${
                  idType === t ? "bg-blue-600 text-white border-blue-600" : "bg-white text-slate-600 border-slate-300"
                }`}>{l}</button>
            ))}
          </div>
          <input className="input uppercase" value={f.cccd}
            placeholder={idType === "cccd" ? "12 chữ số" : "6–9 ký tự chữ/số"}
            onChange={(e) => setF({ ...f, cccd: idType === "cccd"
              ? e.target.value.replace(/\D/g, "")
              : e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "") })} />
        </F>
        <F label="Họ tên"><input className="input" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></F>
        <F label="Ngày sinh"><input type="date" className="input" value={f.birth_date} onChange={(e) => setF({ ...f, birth_date: e.target.value })} /></F>
        <F label="Đơn vị"><input className="input" value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} /></F>
        <F label="Năm tốt nghiệp"><input type="number" className="input" value={f.graduation_year ?? ""} onChange={(e) => setF({ ...f, graduation_year: e.target.value ? Number(e.target.value) : null })} /></F>
        <F label="Ngành"><input className="input" value={f.major ?? ""} onChange={(e) => setF({ ...f, major: e.target.value })} /></F>
        <F label="Đối tượng"><input className="input" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} /></F>
        <F label="Lần dự thi"><input type="number" className="input" value={f.attempt_number ?? 1} onChange={(e) => setF({ ...f, attempt_number: Number(e.target.value) })} /></F>
        <F label="Kỳ thi" span>
          <select className="input" value={f.exam_id ?? ""} onChange={(e) => setF({ ...f, exam_id: e.target.value || null })}>
            <option value="">— Chưa gán —</option>
            {exams.map((ex) => <option key={ex.id} value={ex.id}>{ex.name} ({ex.status})</option>)}
          </select>
        </F>
        {emergency && (
          <F label="Lý do bổ sung" span>
            <textarea className="input" value={reason} onChange={(e) => setReason(e.target.value)} />
          </F>
        )}
      </div>
      {err && <p className="text-sm text-red-600 mt-3">{err}</p>}
      <button onClick={() => { setErr(""); save.mutate(); }} disabled={save.isPending || (emergency && reason.length < 3)}
        className="mt-4 w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700 disabled:opacity-60">
        {save.isPending ? "Đang lưu…" : "Lưu"}
      </button>
    </Modal>
  );
}

function F({ label, children, span }: { label: string; children: React.ReactNode; span?: boolean }) {
  return (
    <div className={span ? "col-span-2" : ""}>
      <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      {children}
    </div>
  );
}
