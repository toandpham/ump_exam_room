import { useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ImagePlus, Pencil, Plus, Shield, Trash2, Upload } from "lucide-react";
import { candidatesApi, type CandidateFilters } from "../api/candidates";
import { uploadUrl, type Candidate } from "../api/types";
import CandidateForm from "../components/CandidateForm";
import BulkImportWizard from "../components/BulkImportWizard";
import SecurityLogModal from "../components/SecurityLogModal";

// Mounted only at /exams/:examId/candidates → always scoped to one exam.
export default function CandidatesPage() {
  const qc = useQueryClient();
  const { examId: scopedExamId } = useParams();
  const [filters, setFilters] = useState<CandidateFilters>({
    page: 1, page_size: 50, exam_id: scopedExamId,
  });
  const { data, isLoading } = useQuery({
    queryKey: ["candidates", filters],
    queryFn: () => candidatesApi.list(filters),
  });

  const [form, setForm] = useState<{ open: boolean; candidate: Candidate | null }>({ open: false, candidate: null });
  const [wizardOpen, setWizardOpen] = useState(false);
  const [logOpen, setLogOpen] = useState(false);
  const photoRef = useRef<HTMLInputElement>(null);
  const [photoTarget, setPhotoTarget] = useState<string | null>(null);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["candidates"] });
    qc.invalidateQueries({ queryKey: ["candidate-stats"] });
  };
  const del = useMutation({ mutationFn: (id: string) => candidatesApi.remove(id), onSuccess: invalidate });
  const photo = useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => candidatesApi.uploadPhoto(id, file),
    onSuccess: invalidate,
  });

  const items = data?.items ?? [];

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-slate-800">Thí sinh đăng ký</h2>
        <div className="flex flex-wrap gap-2">
          <Btn onClick={() => setWizardOpen(true)} icon={Upload}>Nhập danh sách</Btn>
          <Btn onClick={() => candidatesApi.exportXlsx(filters)} icon={Download}>Export</Btn>
          <Btn onClick={() => setLogOpen(true)} icon={Shield}>Nhật ký bảo mật</Btn>
          <Btn onClick={() => setForm({ open: true, candidate: null })} icon={Plus} primary>Thêm thí sinh</Btn>
        </div>
      </div>


      {!isLoading && (data?.total ?? 0) === 0 && (
        <div className="mb-4 rounded-xl border-2 border-dashed border-blue-200 bg-blue-50 p-6 text-center">
          <p className="text-slate-700 font-medium">Bước tiếp theo: nhập danh sách thí sinh cho kỳ thi</p>
          <p className="text-sm text-slate-500 mt-1 mb-3">Tải mẫu Excel, điền danh sách rồi import. Danh sách dùng chung cho mọi buổi thi.</p>
          <button onClick={() => setWizardOpen(true)}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700">
            <Upload size={16} /> Nhập danh sách thí sinh
          </button>
        </div>
      )}

      <div className="flex flex-wrap gap-2 mb-3">
        <input className="input max-w-40" placeholder="CCCD" onChange={(e) => setFilters((f) => ({ ...f, cccd: e.target.value, page: 1 }))} />
        <input className="input max-w-48" placeholder="Họ tên" onChange={(e) => setFilters((f) => ({ ...f, full_name: e.target.value, page: 1 }))} />
        <input className="input max-w-48" placeholder="Đơn vị" onChange={(e) => setFilters((f) => ({ ...f, unit: e.target.value, page: 1 }))} />
        <input className="input max-w-40" placeholder="Đối tượng" onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value, page: 1 }))} />
      </div>

      <input ref={photoRef} type="file" accept="image/*" className="hidden"
        onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; if (file && photoTarget) photo.mutate({ id: photoTarget, file }); }} />

      <div className="bg-white rounded-xl shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-3 py-2">Ảnh</th><th className="px-3 py-2">CCCD / Hộ chiếu</th><th className="px-3 py-2">Họ tên</th>
              <th className="px-3 py-2">Ngày sinh</th><th className="px-3 py-2">Đơn vị</th><th className="px-3 py-2">Ngành</th>
              <th className="px-3 py-2">Đối tượng</th><th className="px-3 py-2">Lần</th><th className="px-3 py-2">Kỳ thi</th>
              <th className="px-3 py-2 text-right">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && <tr><td colSpan={10} className="px-3 py-6 text-center text-slate-400">Đang tải…</td></tr>}
            {items.map((c) => (
              <tr key={c.id} className="hover:bg-slate-50">
                <td className="px-3 py-2">
                  {c.photo_path ? <img src={uploadUrl(c.photo_path)} className="h-10 w-8 object-cover rounded" />
                    : <div className="h-10 w-8 bg-slate-100 rounded flex items-center justify-center text-slate-300 text-xs">—</div>}
                </td>
                <td className="px-3 py-2 font-mono">
                  {c.cccd}
                  {c.id_type === "passport" && (
                    <span className="ml-1.5 px-1 py-0.5 rounded bg-amber-100 text-amber-700 text-[10px] font-sans align-middle">HC</span>
                  )}
                </td>
                <td className="px-3 py-2">{c.full_name}</td>
                <td className="px-3 py-2">{c.birth_date}</td>
                <td className="px-3 py-2">{c.unit}</td>
                <td className="px-3 py-2">{c.major || "—"}</td>
                <td className="px-3 py-2">{c.category}</td>
                <td className="px-3 py-2">{c.attempt_number}</td>
                <td className="px-3 py-2">{c.exam_name || "—"}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center justify-end gap-1">
                    <button title="Ảnh" onClick={() => { setPhotoTarget(c.id); photoRef.current?.click(); }} className="p-1 hover:bg-slate-100 rounded"><ImagePlus size={15} /></button>
                    <button title="Sửa" onClick={() => setForm({ open: true, candidate: c })} className="p-1 hover:bg-slate-100 rounded"><Pencil size={15} /></button>
                    <button title="Xoá" onClick={() => confirm(`Xoá ${c.full_name}?`) && del.mutate(c.id)} className="p-1 hover:bg-slate-100 rounded"><Trash2 size={15} className="text-red-600" /></button>
                  </div>
                </td>
              </tr>
            ))}
            {!isLoading && items.length === 0 && <tr><td colSpan={10} className="px-3 py-6 text-center text-slate-400">Không có thí sinh.</td></tr>}
          </tbody>
        </table>
      </div>
      {data && data.total > (filters.page_size ?? 50) && (
        <div className="flex items-center justify-center gap-3 mt-3 text-sm">
          <button disabled={(filters.page ?? 1) <= 1} onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) - 1 }))} className="px-3 py-1 rounded border disabled:opacity-50">Trước</button>
          <span>Trang {filters.page} / {Math.ceil(data.total / (filters.page_size ?? 50))}</span>
          <button disabled={(filters.page ?? 1) >= Math.ceil(data.total / (filters.page_size ?? 50))} onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) + 1 }))} className="px-3 py-1 rounded border disabled:opacity-50">Sau</button>
        </div>
      )}

      {form.open && <CandidateForm open={form.open} candidate={form.candidate} onClose={() => setForm({ open: false, candidate: null })} />}
      <BulkImportWizard open={wizardOpen} onClose={() => setWizardOpen(false)} lockedExamId={scopedExamId} />
      <SecurityLogModal open={logOpen} onClose={() => setLogOpen(false)} />
    </div>
  );
}

function Btn({ children, onClick, icon: Icon, primary }: {
  children: React.ReactNode; onClick: () => void; icon: any; primary?: boolean;
}) {
  const cls = primary ? "bg-blue-600 text-white hover:bg-blue-700"
    : "border border-slate-300 bg-white hover:bg-slate-50";
  return (
    <button onClick={onClick} className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm ${cls}`}>
      <Icon size={16} /> {children}
    </button>
  );
}
