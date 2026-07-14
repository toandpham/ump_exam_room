import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogIn } from "lucide-react";
import { errorMessage } from "../api/client";
import { authApi } from "../api/auth";
import { useAuthStore } from "../stores/auth";
import { roleLabel, type Role } from "../lib/roles";

// Role-specific login links (Caddy redirects /chutich, /giamthi, /admin here with
// a ?role= hint). The link both labels the screen and restricts which account
// role may sign in there.
const ROLE_BY_HINT: Record<string, Role> = {
  quantri: "super_admin",
  chutich: "proctor",
  giamthi: "room_proctor",
};

export default function LoginPage() {
  const navigate = useNavigate();
  const setToken = useAuthStore((s) => s.setToken);
  const setAdmin = useAuthStore((s) => s.setAdmin);
  const clear = useAuthStore((s) => s.clear);
  const hint = new URLSearchParams(window.location.search).get("role") || "";
  const expectedRole = ROLE_BY_HINT[hint];
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [cooldown, setCooldown] = useState(0);   // seconds left after too many tries

  // Live countdown while locked out (HTTP 429).
  useEffect(() => {
    if (cooldown <= 0) return;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (cooldown > 0) return;
    setError("");
    setLoading(true);
    try {
      const data = await authApi.login(username, password);
      setToken(data.access_token);
      // Enforce the role this login link is for (if any). If /me fails (e.g.
      // network drop) clear the token again — otherwise the store is left with
      // a token but no admin and ProtectedRoute loops.
      let me;
      try {
        me = await authApi.me();
      } catch (err) {
        clear();
        throw err;
      }
      if (expectedRole && me.role !== expectedRole) {
        clear();
        setError(`Tài khoản này là "${roleLabel(me.role)}", không dùng được ở link "${roleLabel(expectedRole)}". Vui lòng dùng đúng link đăng nhập của vai trò bạn.`);
        return;
      }
      setAdmin(me);
      navigate("/", { replace: true });
    } catch (err) {
      const resp = (err as any)?.response;
      if (resp?.status === 429) {
        const secs = Number(resp.data?.retry_after) || Number(resp.headers?.["retry-after"]) || 120;
        setCooldown(secs);
        setError("Đăng nhập sai quá nhiều lần. Vui lòng đợi rồi thử lại.");
      } else {
        setError(errorMessage(err, "Đăng nhập thất bại"));
      }
    } finally {
      setLoading(false);
    }
  }

  const mmss = `${Math.floor(cooldown / 60)}:${String(cooldown % 60).padStart(2, "0")}`;

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-white rounded-xl shadow-md p-8 space-y-5"
      >
        <div className="text-center">
          <h1 className="text-xl font-bold text-slate-800">Phòng thi trực tuyến</h1>
          <p className="text-sm text-slate-500 mt-1">
            {expectedRole
              ? <>Đăng nhập <span className="font-semibold text-blue-700">{roleLabel(expectedRole)}</span></>
              : "Đăng nhập để tiếp tục"}
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Tên đăng nhập</label>
          <input
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Mật khẩu</label>
          <input
            type="password"
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        {cooldown > 0 && (
          <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 text-center">
            Thử lại sau <span className="font-mono font-bold">{mmss}</span>
          </p>
        )}
        <button
          type="submit"
          disabled={loading || cooldown > 0}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-medium py-2 rounded-lg transition"
        >
          <LogIn size={18} />
          {cooldown > 0 ? `Đợi ${mmss}` : loading ? "Đang đăng nhập…" : "Đăng nhập"}
        </button>
      </form>
    </div>
  );
}
