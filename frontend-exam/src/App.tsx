import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MonitorX } from "lucide-react";
import { examApi } from "./api/exam";
import { useStore } from "./store";
import { useExamSocket, type WsEvent } from "./hooks/useExamSocket";
import LoginScreen from "./screens/LoginScreen";
import ConfirmScreen from "./screens/ConfirmScreen";
import StatusScreen from "./screens/StatusScreen";
import ExamScreen from "./screens/ExamScreen";
import SebRequiredScreen from "./screens/SebRequiredScreen";
import LicenseBlockedScreen from "./screens/LicenseBlockedScreen";
import NoExamScreen from "./screens/NoExamScreen";
import CountdownScreen from "./screens/CountdownScreen";

export default function App() {
  const token = useStore((s) => s.token);
  if (!token) return <LoginGate />;
  return <ExamShell />;
}

/** Before showing the login form, confirm an exam is actually running. No exam
 * running -> NoExamScreen; the poll auto-switches to login when a buổi opens
 * (AD-61). SEB note: enforcement is OFF since AD-64 (máy thi dùng Firefox/kiosk
 * Electron) so the 403 `seb_required` branch below is dormant — kept as an escape
 * hatch in case SEB_ENFORCE is turned back on for Win10/11 machines. */
function LoginGate() {
  const { data: status, isLoading, error } = useQuery({
    queryKey: ["exam-status"],
    queryFn: examApi.status,
    refetchInterval: 10000,   // AD-69: giãn poll (giảm tải server cho ~1000 máy)
    retry: false,
  });

  const sebRequired =
    axios.isAxiosError(error) &&
    error.response?.status === 403 &&
    (error.response?.data as any)?.detail?.code === "seb_required";
  if (sebRequired) return <SebRequiredScreen />;

  // AD-74: giấy phép server hết hạn/thiếu → middleware chặn /status bằng 403
  // license_* (code ở cấp cao nhất của body, khác shape với seb_required).
  const licenseBlocked =
    axios.isAxiosError(error) &&
    error.response?.status === 403 &&
    String((error.response?.data as any)?.code ?? "").startsWith("license_");
  if (licenseBlocked) return <LicenseBlockedScreen />;

  if (isLoading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">Đang tải…</div>;
  }
  if (!status?.open) return <NoExamScreen />;
  return <LoginScreen />;
}

function ExamShell() {
  const qc = useQueryClient();
  const logout = useStore((s) => s.logout);
  const candidate = useStore((s) => s.candidate);
  const setIdentity = useStore((s) => s.setIdentity);
  // SP-2c: id PHIÊN đã qua đếm ngược → chuyển sang ExamScreen. Keyed theo session
  // thay vì boolean + effect reset theo [session_id]: effect reset (cha) chạy SAU
  // onStart của CountdownScreen (con) trong cùng commit mount nên đè mất cờ →
  // reconnect/vào trễ kẹt vĩnh viễn ở màn đếm ngược 0 (bug thực địa 13-07).
  // Buổi mới = session_id mới → tự không khớp → đếm ngược lại, không cần reset.
  const [startedSession, setStartedSession] = useState<string | null>(null);

  // Restore identity from the server after a reload (store keeps only the
  // token). Authoritative — the displayed name always matches the token.
  const { data: me } = useQuery({
    queryKey: ["me"], queryFn: examApi.me, retry: false, enabled: !candidate,
  });
  useEffect(() => {
    if (me?.candidate && !candidate) setIdentity(me.candidate, me.exam ?? null);
  }, [me, candidate, setIdentity]);

  const { data: state, isLoading, error } = useQuery({
    queryKey: ["state"],
    queryFn: examApi.state,
    // AD-69: giãn poll (WS đẩy chuyển trạng thái tức thì). NHƯNG khi 'ready' (chờ
    // "Bắt đầu thi") poll nhanh 5s làm fallback: máy nào rớt WS vẫn nhận start_at
    // trong ≤5s « lead 30s → không lỡ mốc đếm ngược, vào đề đồng loạt (chống giật).
    refetchInterval: (query) => (query.state.data?.status === "ready" ? 5000 : 15000),
    retry: false,
  });

  // SP-2b: tải sẵn đề (đã trộn) NGAY khi 'ready' để 'Bắt đầu' vào tức thì + rải cú
  // tải suốt thời gian chờ. staleTime Infinity → không tải lại khi vào in_progress.
  const prefetch = useQuery({
    queryKey: ["questions"],
    queryFn: examApi.questions,
    enabled: !!state?.session_id && (state?.status === "ready" || state?.status === "in_progress"),
    staleTime: Infinity,
    retry: false,
  });
  useEffect(() => {
    if (state?.status !== "ready" || !prefetch.data) return;
    // Warm cache trình duyệt cho ẢNH (phần nặng) trong lúc chờ.
    for (const q of prefetch.data.questions) {
      q.images.forEach((u) => { new Image().src = u; });
      q.options.forEach((o) => o.images.forEach((u) => { new Image().src = u; }));
    }
  }, [state?.status, prefetch.data]);

  // ONE socket per candidate (AD-14): ExamShell owns it. Every control event
  // refreshes state (instant distribute/start/end transitions) and is forwarded
  // to the active exam session (useExamSession subscribes for exam_ended). This
  // avoids a second connection + double-handling of exam_ended.
  const handlersRef = useRef(new Set<(e: WsEvent) => void>());
  const { send } = useExamSocket(state?.session_id ?? null, (e) => {
    qc.invalidateQueries({ queryKey: ["state"] });
    handlersRef.current.forEach((h) => h(e));
  });
  const subscribe = useCallback((h: (e: WsEvent) => void) => {
    handlersRef.current.add(h);
    return () => { handlersRef.current.delete(h); };
  }, []);

  // Kicked out because the same CCCD logged in on another device.
  const superseded =
    axios.isAxiosError(error) &&
    error.response?.status === 409 &&
    (error.response?.data as any)?.detail?.code === "device_superseded";
  if (superseded) return <KickedScreen onRelogin={logout} />;

  // SEB enforcement is OFF since AD-64 (escape hatch kept): if SEB_ENFORCE is
  // re-enabled, a request from outside Safe Exam Browser returns 403 seb_required.
  const sebRequired =
    axios.isAxiosError(error) &&
    error.response?.status === 403 &&
    (error.response?.data as any)?.detail?.code === "seb_required";
  if (sebRequired) return <SebRequiredScreen />;

  // AD-74: giấy phép hết hạn giữa chừng — hiện màn tạm ngưng thay vì lỗi mù.
  const licenseBlocked =
    axios.isAxiosError(error) &&
    error.response?.status === 403 &&
    String((error.response?.data as any)?.code ?? "").startsWith("license_");
  if (licenseBlocked) return <LicenseBlockedScreen />;

  if (isLoading || !state) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">Đang tải…</div>;
  }

  const refresh = () => qc.invalidateQueries({ queryKey: ["state"] });

  // No session yet -> confirm info first.
  if (!state.session_id || state.status == null) return <ConfirmScreen onConfirmed={refresh} />;

  switch (state.status) {
    case "waiting":
      return <StatusScreen variant="waiting" />;
    case "ready":
      return <StatusScreen variant="ready" />;
    case "in_progress":
      // SP-2c: nếu chưa tới mốc bắt đầu chung → đếm ngược đồng bộ (đề đã prefetch,
      // mở tức thì khi tới giờ). CountdownScreen tự gọi onStart ngay nếu đã qua giờ.
      if (startedSession !== state.session_id && state.started_at) {
        const sid = state.session_id;
        return (
          <CountdownScreen
            startAt={state.started_at}
            serverTime={state.server_time}
            onStart={() => setStartedSession(sid)}
            examName={me?.exam?.name}
          />
        );
      }
      return <ExamScreen sessionId={state.session_id} onSubmitted={refresh} ws={{ send, subscribe }} />;
    case "submitted":
    case "timeout":
      return <StatusScreen variant="result" submittedAt={state.submitted_at} />;
    default:
      return <StatusScreen variant="waiting" />;
  }
}

function KickedScreen({ onRelogin }: { onRelogin: () => void }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-lg p-8 text-center">
        <div className="mx-auto w-16 h-16 rounded-full bg-rose-100 flex items-center justify-center mb-4">
          <MonitorX size={32} className="text-rose-600" />
        </div>
        <h1 className="text-xl font-bold text-slate-800">Phiên đã kết thúc</h1>
        <p className="text-sm text-slate-600 mt-2">
          Phiên trên thiết bị này đã bị thoát — do tài khoản của bạn được đăng nhập ở một
          thiết bị khác, hoặc do giám thị đăng xuất giúp bạn. Nếu bạn không rõ lý do,
          hãy báo ngay cho giám thị.
        </p>
        <button onClick={onRelogin}
          className="mt-5 w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg">
          Về trang đăng nhập
        </button>
      </div>
    </div>
  );
}
