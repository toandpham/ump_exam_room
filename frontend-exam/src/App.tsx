import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MonitorX } from "lucide-react";
import { examApi } from "./api/exam";
import { useStore } from "./store";
import { useExamSocket, type WsEvent } from "./hooks/useExamSocket";
import { usePreloadDeck } from "./hooks/usePreloadDeck";
import { useBlockedScreen } from "./hooks/useBlockedScreen";
import LoginScreen from "./screens/LoginScreen";
import ConfirmScreen from "./screens/ConfirmScreen";
import StatusScreen from "./screens/StatusScreen";
import ExamScreen from "./screens/ExamScreen";
import KioskRequiredScreen from "./screens/KioskRequiredScreen";
import LicenseBlockedScreen from "./screens/LicenseBlockedScreen";
import NoExamScreen from "./screens/NoExamScreen";
import CountdownScreen from "./screens/CountdownScreen";

export default function App() {
  const token = useStore((s) => s.token);
  const qc = useQueryClient();

  // AD-90d: đăng xuất (tự động sau khi xem kết quả, giám thị đá ra, hay bị đá vì
  // đăng nhập máy khác) → XOÁ SẠCH bộ nhớ đệm của trang: đề, trạng thái, danh tính.
  // Không có bước này thì thí sinh kế ngồi vào CÙNG trình duyệt (máy không tải lại
  // trang) có thể thấy lại dữ liệu của người trước / của buổi trước.
  useEffect(() => {
    if (!token) qc.clear();
  }, [token, qc]);

  return !token ? <LoginGate /> : <ExamShell />;
}

/** Before showing the login form, confirm an exam is actually running. No exam
 * running -> NoExamScreen; the poll auto-switches to login when a buổi opens
 * (AD-61). */
function LoginGate() {
  const { data: status, isLoading, error } = useQuery({
    queryKey: ["exam-status"],
    queryFn: examApi.status,
    refetchInterval: 10000,   // AD-69: giãn poll (giảm tải server cho ~1000 máy)
    retry: false,
  });

  const blocked = useBlockedScreen(error);
  if (blocked === "kiosk") return <KioskRequiredScreen />;      // AD-91
  if (blocked === "license") return <LicenseBlockedScreen />;   // AD-74

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
    // AD-90d: khoá theo PHIÊN. Trước đây khoá chung ["questions"] + staleTime vô hạn
    // → máy KHÔNG tải lại trang (thí sinh kế đăng nhập trên cùng trình duyệt, hoặc
    // buổi mới mở) vẫn dùng lại ĐỀ CŨ còn nằm trong bộ nhớ trang. Mỗi buổi là một
    // phiên khác nhau nên khoá theo session_id là hết sạch nguy cơ lẫn đề.
    queryKey: ["questions", state?.session_id],
    queryFn: examApi.questions,
    enabled: !!state?.session_id && (state?.status === "ready" || state?.status === "in_progress"),
    staleTime: Infinity,
    retry: false,
  });
  // AD-110/AD-110b: nạp trước ảnh đề + báo server khi tải đủ (gate "Bắt đầu thi").
  // Chi tiết semantics nằm trong hook — tách ở refactor đợt 3 để App.tsx còn là
  // bộ định tuyến màn hình.
  const { download } = usePreloadDeck(state?.status, state?.session_id, prefetch.data);

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

  const blocked = useBlockedScreen(error);
  if (blocked === "kicked") return <KickedScreen onRelogin={logout} />;   // AD-26
  if (blocked === "kiosk") return <KioskRequiredScreen />;                // AD-91
  if (blocked === "license") return <LicenseBlockedScreen />;             // AD-74

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
      return <StatusScreen variant="ready" download={download} />;
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
