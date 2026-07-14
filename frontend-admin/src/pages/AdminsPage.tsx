import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, UserPlus } from "lucide-react";
import { adminsApi, type AdminAccount, type AdminCreate } from "../api/admins";
import { errorMessage } from "../api/client";
import { useAuthStore } from "../stores/auth";
import { roleLabel } from "../lib/roles";
import Modal from "../components/Modal";
import Field from "../components/Field";

export default function AdminsPage() {
  const me = useAuthStore((s) => s.admin);
  const { data: admins = [], isLoading } = useQuery({
    queryKey: ["admins"], queryFn: adminsApi.list,
  });
  const [createOpen, setCreateOpen] = useState(false);
  const [pwTarget, setPwTarget] = useState<AdminAccount | null>(null);

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-2xl font-bold text-slate-800">Tài khoản quản trị / giám thị</h1>
        <button onClick={() => setCreateOpen(true)}
          className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700">
          <UserPlus size={16} /> Thêm tài khoản
        </button>
      </div>
      <p className="text-sm text-slate-500 mb-4">
        Tạo tài khoản giám thị và đổi mật khẩu. Đăng nhập chỉ cần tên đăng nhập + mật khẩu.
      </p>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 text-sm text-blue-800 mb-4">
        ℹ️ Nếu super_admin quên mật khẩu và không có super_admin khác để đặt lại, chạy lệnh trên máy chủ:
        <code className="block mt-1 bg-white/70 rounded px-2 py-1 text-xs">
          docker compose exec backend python -m app.reset_password &lt;tên đăng nhập&gt; &lt;mật khẩu mới&gt;
        </code>
      </div>

      <div className="bg-white rounded-xl shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2">Tên đăng nhập</th>
              <th className="px-4 py-2">Họ tên</th>
              <th className="px-4 py-2">Vai trò</th>
              <th className="px-4 py-2 text-right">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && <tr><td colSpan={4} className="px-4 py-6 text-center text-slate-400">Đang tải…</td></tr>}
            {admins.map((a) => (
              <Row key={a.id} a={a} isSelf={a.id === me?.id} onSetPw={() => setPwTarget(a)} />
            ))}
          </tbody>
        </table>
      </div>

      {createOpen && <CreateModal onClose={() => setCreateOpen(false)} />}
      {pwTarget && <PasswordModal account={pwTarget} onClose={() => setPwTarget(null)} />}
    </div>
  );
}

function Row({ a, isSelf, onSetPw }: { a: AdminAccount; isSelf: boolean; onSetPw: () => void }) {
  return (
    <tr className="hover:bg-slate-50">
      <td className="px-4 py-2 font-mono">{a.username}{isSelf && <span className="ml-2 text-xs text-blue-600">(bạn)</span>}</td>
      <td className="px-4 py-2">{a.full_name || "—"}</td>
      <td className="px-4 py-2">{roleLabel(a.role)}</td>
      <td className="px-4 py-2">
        <div className="flex items-center justify-end">
          <button onClick={onSetPw}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 text-sm">
            <KeyRound size={15} /> Đổi mật khẩu
          </button>
        </div>
      </td>
    </tr>
  );
}

function CreateModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [form, setForm] = useState<AdminCreate>({ username: "", password: "", full_name: "", role: "proctor" });
  const create = useMutation({
    mutationFn: () => adminsApi.create(form),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admins"] }); onClose(); },
  });
  return (
    <Modal open title="Thêm tài khoản" onClose={onClose} width="max-w-md">
      <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="space-y-3">
        <Field label="Tên đăng nhập">
          <input className="input" value={form.username} autoFocus
            onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))} />
        </Field>
        <Field label="Họ tên">
          <input className="input" value={form.full_name ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} />
        </Field>
        <Field label="Vai trò">
          <select className="input" value={form.role}
            onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
            <option value="proctor">Chủ tịch hội đồng thi</option>
            <option value="room_proctor">Giám thị</option>
            <option value="super_admin">Quản trị (super admin)</option>
          </select>
        </Field>
        <Field label="Mật khẩu (tối thiểu 6 ký tự)">
          <input type="text" className="input" value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
        </Field>
        {create.isError && <p className="text-sm text-rose-700">{errorMessage(create.error)}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg border text-sm">Huỷ</button>
          <button type="submit" disabled={create.isPending || form.username.length < 3 || form.password.length < 6}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm disabled:opacity-50">
            {create.isPending ? "Đang tạo…" : "Tạo tài khoản"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function PasswordModal({ account, onClose }: { account: AdminAccount; onClose: () => void }) {
  const qc = useQueryClient();
  const [pw, setPw] = useState("");
  const save = useMutation({
    mutationFn: () => adminsApi.setPassword(account.id, pw),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admins"] }); onClose(); },
  });
  return (
    <Modal open title={`Đổi mật khẩu — ${account.username}`} onClose={onClose} width="max-w-md">
      <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="space-y-3">
        <Field label="Mật khẩu mới (tối thiểu 6 ký tự)">
          <input type="text" className="input" value={pw} autoFocus
            onChange={(e) => setPw(e.target.value)} />
        </Field>
        {save.isError && <p className="text-sm text-rose-700">{errorMessage(save.error)}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg border text-sm">Huỷ</button>
          <button type="submit" disabled={save.isPending || pw.length < 6}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm disabled:opacity-50">
            {save.isPending ? "Đang lưu…" : "Lưu mật khẩu"}
          </button>
        </div>
      </form>
    </Modal>
  );
}

