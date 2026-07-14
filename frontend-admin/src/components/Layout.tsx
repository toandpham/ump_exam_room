import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { BadgeCheck, ChevronLeft, ChevronRight, ClipboardList, DoorOpen, KeyRound, LayoutDashboard, LogOut, ScrollText, Users2 } from "lucide-react";
import { errorMessage } from "../api/client";
import { authApi } from "../api/auth";
import { adminsApi } from "../api/admins";
import { useAuthStore } from "../stores/auth";
import { roleLabel } from "../lib/roles";
import Modal from "./Modal";
import Field from "./Field";

// Role-split navigation (AD-47):
// - Chủ tịch hội đồng thi (proctor) orchestrate exams → "Kỳ thi" (full dashboard).
// - Giám thị (room_proctor) supervise their room → "Phòng của tôi".
// - Quản trị (super_admin) manage the system → Dashboard + Kỳ thi (view/delete) + Nhật ký + Tài khoản.
const PROCTOR_NAV = [
  { to: "/exams", label: "Kỳ thi", icon: ClipboardList },
];
const ROOM_PROCTOR_NAV = [
  { to: "/my-rooms", label: "Phòng của tôi", icon: DoorOpen },
];
const SUPER_NAV = [
  { to: "/dashboard", label: "Bảng điều khiển", icon: LayoutDashboard },
  { to: "/exams", label: "Kỳ thi", icon: ClipboardList },
  { to: "/audit", label: "Nhật ký", icon: ScrollText },
  { to: "/admins", label: "Tài khoản", icon: Users2 },
  { to: "/license", label: "Giấy phép", icon: BadgeCheck },
];

function navFor(role: string | undefined) {
  if (role === "super_admin") return SUPER_NAV;
  if (role === "room_proctor") return ROOM_PROCTOR_NAV;
  return PROCTOR_NAV;
}

export default function Layout() {
  const navigate = useNavigate();
  const admin = useAuthStore((s) => s.admin);
  const clear = useAuthStore((s) => s.clear);
  const nav = navFor(admin?.role);
  const [pwOpen, setPwOpen] = useState(false);

  // Collapse the sidebar to an icon rail to free up horizontal space (e.g. on
  // the monitor screen's wide table). Persisted across reloads.
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("nav_collapsed") === "1");
  function toggle() {
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem("nav_collapsed", next ? "1" : "0");
      return next;
    });
  }

  async function logout() {
    try {
      await authApi.logout();
    } catch {
      /* ignore */
    }
    clear();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen flex bg-slate-100">
      <aside className={`${collapsed ? "w-16" : "w-60"} bg-slate-900 text-slate-200 flex flex-col transition-all duration-200`}>
        <div className="flex items-center justify-between px-3 py-4 border-b border-slate-700 h-[57px]">
          {!collapsed && <span className="text-lg font-bold truncate pl-2">Phòng thi trực tuyến</span>}
          <button
            onClick={toggle}
            title={collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên"}
            className="p-1.5 rounded-lg hover:bg-slate-800 shrink-0 mx-auto"
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              title={collapsed ? label : undefined}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition ${
                  collapsed ? "justify-center" : ""
                } ${isActive ? "bg-blue-600 text-white" : "hover:bg-slate-800"}`
              }
            >
              <Icon size={18} className="shrink-0" />
              {!collapsed && label}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={logout}
          title={collapsed ? "Đăng xuất" : undefined}
          className={`m-3 flex items-center gap-2 px-3 py-2 rounded-lg text-sm hover:bg-slate-800 ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <LogOut size={18} className="shrink-0" />
          {!collapsed && "Đăng xuất"}
        </button>
      </aside>
      <div className="flex-1 flex flex-col min-w-0">
        <header className="h-14 bg-white border-b border-slate-200 flex items-center justify-end gap-3 px-6">
          {/* Show the ROLE as the identity, not the account's full_name — the
              name can be misleading (e.g. a "Giám thị 1"–named account that is
              actually the chủ tịch). The username stays as a small disambiguator. */}
          <span className="text-sm font-medium text-slate-700">
            {roleLabel(admin?.role)}
            {admin?.username && <span className="ml-1.5 text-xs font-normal text-slate-400">@{admin.username}</span>}
          </span>
          <button onClick={() => setPwOpen(true)}
            className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800 border border-slate-200 rounded-lg px-2.5 py-1.5">
            <KeyRound size={15} /> Đổi mật khẩu
          </button>
        </header>
        <main className="flex-1 p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
      {pwOpen && <ChangePasswordModal onClose={() => setPwOpen(false)} />}
    </div>
  );
}

function ChangePasswordModal({ onClose }: { onClose: () => void }) {
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (newPw.length < 6) { setError("Mật khẩu mới tối thiểu 6 ký tự."); return; }
    if (newPw !== confirm) { setError("Xác nhận mật khẩu không khớp."); return; }
    setBusy(true);
    try {
      await adminsApi.changeMyPassword(oldPw, newPw);
      setDone(true);
    } catch (err) {
      setError(errorMessage(err, "Đổi mật khẩu thất bại"));
    } finally { setBusy(false); }
  }

  return (
    <Modal open title="Đổi mật khẩu" onClose={onClose} width="max-w-sm">
      {done ? (
        <div className="text-center py-4">
          <p className="text-green-700 font-medium">✓ Đã đổi mật khẩu thành công.</p>
          <button onClick={onClose} className="mt-4 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm">Đóng</button>
        </div>
      ) : (
          <form onSubmit={submit} className="space-y-3">
            <Field label="Mật khẩu hiện tại">
              <input type="password" className="input" value={oldPw} autoFocus
                onChange={(e) => setOldPw(e.target.value)} />
            </Field>
            <Field label="Mật khẩu mới (tối thiểu 6 ký tự)">
              <input type="password" className="input" value={newPw}
                onChange={(e) => setNewPw(e.target.value)} />
            </Field>
            <Field label="Nhập lại mật khẩu mới">
              <input type="password" className="input" value={confirm}
                onChange={(e) => setConfirm(e.target.value)} />
            </Field>
            {error && <p className="text-sm text-rose-700">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg border text-sm">Huỷ</button>
              <button type="submit" disabled={busy || !oldPw || !newPw}
                className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm disabled:opacity-50">
                {busy ? "Đang đổi…" : "Đổi mật khẩu"}
              </button>
            </div>
          </form>
      )}
    </Modal>
  );
}
