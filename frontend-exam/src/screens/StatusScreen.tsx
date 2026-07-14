import { useEffect, useState } from "react";
import { Award, CheckCircle2, Clock, Hourglass } from "lucide-react";
import { examApi } from "../api/exam";
import { photoUrl, useStore } from "../store";

interface Props {
  variant: "waiting" | "ready" | "result";
  submittedAt?: string | null;
}

interface ResultData {
  status: string;
  submitted_at: string | null;
  total: number;
  answered: number;
  total_correct: number;
}

// Sau khi xem kết quả, tự đăng xuất để nhường máy cho thí sinh kế (cuộc thi liền
// sau) — không cần giám thị thao tác (AD-69).
const AUTO_LOGOUT_SECONDS = 30;

export default function StatusScreen({ variant, submittedAt }: Props) {
  const { candidate, exam, logout } = useStore();
  const [result, setResult] = useState<ResultData | null>(null);
  const [loadingResult, setLoadingResult] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(AUTO_LOGOUT_SECONDS);

  useEffect(() => {
    if (variant !== "result") return;
    setLoadingResult(true);
    examApi.result()
      .then((r) => setResult(r))
      .catch(() => setResult(null))
      .finally(() => setLoadingResult(false));
  }, [variant]);

  // Đếm ngược rồi tự đăng xuất về màn đăng nhập. Tách interval (hiển thị) khỏi
  // timeout (đăng xuất) cho chắc; cả hai dọn khi rời màn.
  useEffect(() => {
    if (variant !== "result") return;
    const tick = setInterval(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    const done = setTimeout(logout, AUTO_LOGOUT_SECONDS * 1000);
    return () => { clearInterval(tick); clearTimeout(done); };
  }, [variant, logout]);

  if (variant === "result") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
        <div className="w-full max-w-md bg-white rounded-2xl shadow-lg p-8 text-center">
          {candidate && (
            <div className="flex items-center justify-center gap-3 mb-5">
              {candidate.photo_path && (
                <img src={photoUrl(candidate.photo_path)} className="w-12 h-14 object-cover rounded border bg-slate-100" />
              )}
              <div className="text-left">
                <p className="font-semibold text-slate-800">{candidate.full_name}</p>
                <p className="text-xs text-slate-500">{exam?.name}</p>
              </div>
            </div>
          )}
          <div className="flex justify-center mb-3">
            <CheckCircle2 className="text-green-500" size={48} />
          </div>
          <h1 className="text-xl font-bold text-slate-800">
            {result?.status === "timeout" ? "Đã hết giờ — bài đã được nộp" : "Đã nộp bài thành công"}
          </h1>
          {submittedAt && (
            <p className="text-xs text-slate-500 mt-1">
              {new Date(submittedAt).toLocaleString("vi-VN")}
            </p>
          )}

          {loadingResult ? (
            <p className="mt-6 text-slate-400 text-sm">Đang chấm điểm…</p>
          ) : result ? (
            <div className="mt-6 p-5 bg-gradient-to-b from-blue-50 to-white rounded-xl border border-blue-100">
              <div className="flex items-center justify-center gap-2 text-blue-600 mb-2">
                <Award size={20} /> <span className="text-sm font-semibold">Kết quả</span>
              </div>
              <div className="text-5xl font-bold text-slate-800">
                {result.total_correct}<span className="text-2xl text-slate-400">/{result.total}</span>
              </div>
              <p className="text-sm text-slate-500 mt-1">câu đúng</p>
              {result.answered < result.total && (
                <p className="mt-3 text-xs text-amber-600">
                  Bạn đã trả lời {result.answered}/{result.total} câu.
                </p>
              )}
            </div>
          ) : (
            <p className="mt-6 text-slate-400 text-sm">Không lấy được kết quả.</p>
          )}

          <p className="mt-6 text-xs text-slate-400">
            Kết quả đã được hệ thống niêm phong (SHA-256). Mọi thay đổi sau khi nộp đều bị phát hiện.
          </p>
          {/* Tự đăng xuất sau 30s để nhường máy cho thí sinh kế (không cần giám thị). */}
          <p className="mt-5 text-sm text-slate-500">
            Tự động đăng xuất sau <span className="font-semibold text-slate-700">{secondsLeft}s</span> để
            nhường máy cho thí sinh tiếp theo.
          </p>
          <button onClick={logout}
            className="mt-3 w-full rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium py-2.5">
            Đăng xuất ngay — trả máy cho thí sinh khác
          </button>
        </div>
      </div>
    );
  }

  const content = variant === "waiting"
    ? { icon: <Hourglass className="text-blue-500" size={48} />,
        title: "Đang chờ hội đồng thi phát đề…", sub: "Vui lòng giữ nguyên màn hình." }
    : { icon: <Clock className="text-blue-500" size={48} />,
        title: "Đề đã sẵn sàng", sub: "Chờ hội đồng thi bắt đầu thi…" };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-lg p-8 text-center">
        {candidate && (
          <div className="flex items-center justify-center gap-3 mb-5">
            {candidate.photo_path && (
              <img src={photoUrl(candidate.photo_path)} className="w-12 h-14 object-cover rounded border bg-slate-100" />
            )}
            <div className="text-left">
              <p className="font-semibold text-slate-800">{candidate.full_name}</p>
              <p className="text-xs text-slate-500">{exam?.name}</p>
            </div>
          </div>
        )}
        <div className="flex justify-center mb-3">{content.icon}</div>
        <h1 className="text-xl font-bold text-slate-800">{content.title}</h1>
        <p className="text-slate-500 mt-1">{content.sub}</p>
        {variant === "ready" && exam && (
          <p className="mt-4 text-sm text-slate-600">Thời gian làm bài: <strong>{exam.duration_minutes} phút</strong></p>
        )}
      </div>
    </div>
  );
}
