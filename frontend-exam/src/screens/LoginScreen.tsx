import { useState } from "react";
import axios from "axios";
import { useQuery } from "@tanstack/react-query";
import { LogIn, UserPlus } from "lucide-react";
import { examApi } from "../api/exam";
import { errorMessage } from "../api/client";
import { useStore } from "../store";
import IdentityInput, { type IdType, ID_ERROR, validateId } from "../components/IdentityInput";
import RegisterScreen from "./RegisterScreen";
import SebRequiredScreen from "./SebRequiredScreen";

export default function LoginScreen() {
  const login = useStore((s) => s.login);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [idType, setIdType] = useState<IdType>("cccd");
  const [cccd, setCccd] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  // SEB enforcement is OFF since AD-64 (máy thi dùng Firefox / kiosk Electron).
  // This stays as an escape hatch: nếu bật lại SEB_ENFORCE, login trả 403
  // seb_required → hiện SebRequiredScreen.
  const [sebBlocked, setSebBlocked] = useState(false);
  const [takeover, setTakeover] = useState(false);
  // Only offer on-the-spot registration if the open exam allows it (AD-33).
  const { data: activeExams } = useQuery({ queryKey: ["active-exams"], queryFn: examApi.activeExams });
  const canRegister = (activeExams ?? []).some((e) => e.allow_registration);

  if (sebBlocked) return <SebRequiredScreen />;

  if (mode === "register") {
    return <RegisterScreen onBack={() => setMode("login")} />;
  }

  function pickType(t: IdType) {
    setIdType(t);
    setCccd("");
    setError("");
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!validateId(idType, cccd)) {
      setError(ID_ERROR[idType]);
      return;
    }
    await doLogin(false);
  }

  async function doLogin(force: boolean) {
    setLoading(true);
    setError("");
    try {
      // "Xếp hàng" chống bão đăng nhập: ở lần đăng nhập đầu (không phải takeover),
      // đợi ngẫu nhiên một chút để 1000 máy không cùng gửi trong một giây — trải tải
      // ra. KHÔNG retry; thí sinh chỉ thấy trạng thái "đang đăng nhập" trong lúc chờ.
      if (!force) await new Promise((r) => setTimeout(r, Math.random() * 2500));
      const res = await examApi.login(cccd, force);
      if (res.requires_takeover) {
        setTakeover(true);   // hỏi xác nhận bằng modal trong trang (không confirm() gốc)
        return;
      }
      if (res.token) login(res.token, res.candidate, res.exam);
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 403 &&
          (err.response?.data as any)?.detail?.code === "seb_required") {
        setSebBlocked(true);
        return;
      }
      setError(errorMessage(err, "Đăng nhập thất bại. Vui lòng thử lại."));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      {takeover && (
        <div className="fixed inset-0 z-50 bg-slate-900/80 flex items-center justify-center backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-2xl p-7 max-w-sm w-full text-center">
            <h2 className="text-xl font-bold text-slate-800">Đăng nhập tại máy này?</h2>
            <p className="text-sm text-slate-600 mt-2">
              CCCD này đang đăng nhập ở một thiết bị khác. Nếu tiếp tục, phiên trên thiết bị kia sẽ bị
              thoát và bạn làm bài tại đây (giám thị sẽ được thông báo).
            </p>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setTakeover(false)}
                className="flex-1 py-2.5 rounded-lg border border-slate-300 text-slate-700 font-medium hover:bg-slate-50">
                Huỷ
              </button>
              <button onClick={() => { setTakeover(false); doLogin(true); }}
                className="flex-1 py-2.5 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700">
                Đăng nhập tại đây
              </button>
            </div>
          </div>
        </div>
      )}
      <form onSubmit={submit} className="w-full max-w-md bg-white rounded-2xl shadow-lg p-8 space-y-5">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-slate-800">Phòng thi trực tuyến</h1>
          <p className="text-slate-500 mt-1">Đã có trong danh sách? Chọn loại giấy tờ và nhập số để vào thi.</p>
        </div>
        <IdentityInput
          variant="login"
          idType={idType}
          value={cccd}
          onIdTypeChange={pickType}
          onValueChange={setCccd}
          autoFocus
        />
        {error && <p className="text-sm text-red-600 text-center">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white font-medium py-3 rounded-lg text-lg"
        >
          <LogIn size={20} />
          {loading ? "Đang đăng nhập, vui lòng đợi…" : "Vào thi"}
        </button>

        {canRegister && (
          <>
            <div className="flex items-center gap-3 text-xs text-slate-400">
              <div className="flex-1 h-px bg-slate-200" /> hoặc <div className="flex-1 h-px bg-slate-200" />
            </div>
            <button
              type="button"
              onClick={() => setMode("register")}
              className="w-full flex items-center justify-center gap-2 border border-slate-300 hover:bg-slate-50 text-slate-700 font-medium py-3 rounded-lg"
            >
              <UserPlus size={18} /> Đăng ký tại chỗ
            </button>
            <p className="text-xs text-center text-slate-400">
              Chưa có trong danh sách? Bấm đăng ký để tự khai báo và vào thi ngay.
            </p>
          </>
        )}
      </form>
    </div>
  );
}
