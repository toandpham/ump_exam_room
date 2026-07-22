import { useCallback, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Calculator, FlaskConical, Hourglass, NotebookPen, Pause, Wifi, WifiOff } from "lucide-react";
import { examApi } from "../api/exam";
import { photoUrl, useStore } from "../store";
import { useExamSession, type SaveStatus, type ExamWs } from "../hooks/useExamSession";
import ScientificCalculator from "../components/ScientificCalculator";
import LabReference from "../components/LabReference";
import QuestionNotes, { clearNotes } from "../components/QuestionNotes";
import QuestionNavigator from "./exam/QuestionNavigator";
import QuestionCard from "./exam/QuestionCard";
import { PRELOAD_AHEAD, imageUrlsOf, preloadImages } from "../lib/preload";

export default function ExamScreen({ sessionId, onSubmitted, ws }: { sessionId: string; onSubmitted: () => void; ws: ExamWs }) {
  const candidate = useStore((s) => s.candidate);
  // Dùng lại đề đã prefetch ở 'ready' (App.tsx) — staleTime Infinity nên KHÔNG tải lại
  // lúc 'Bắt đầu' (tránh burst 1000 request questions cùng lúc).
  const { data } = useQuery({ queryKey: ["questions"], queryFn: examApi.questions, staleTime: Infinity, retry: false });

  const [current, setCurrent] = useState(0);
  const [calcOpen, setCalcOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  const [refOpen, setRefOpen] = useState(false);
  const [submitOpen, setSubmitOpen] = useState(false);
  // Nộp/hết giờ → xoá giấy nháp của phiên rồi chuyển sang màn kết quả.
  const handleSubmitted = () => { clearNotes(sessionId); onSubmitted(); };
  const { answers, selectOption, saveStatus, secondsLeft, paused, timeUp, doSubmit, tabCount,
          submitError, clearSubmitError } =
    useExamSession(sessionId, data, handleSubmitted, ws);

  // AD-90: nạp trước ảnh của vài câu KẾ TIẾP (thay vì cả đề một lúc lúc phát đề —
  // máy Win7/4GB không chịu nổi). Chạy sau khi câu hiện tại đã hiển thị.
  useEffect(() => {
    if (!data) return;
    preloadImages(imageUrlsOf(data.questions.slice(current + 1, current + 1 + PRELOAD_AHEAD)));
  }, [current, data]);

  // Jump to the next still-unanswered question, scanning forward from the
  // current position and wrapping back to the start. Lets candidates triage hard
  // questions and return without scrubbing the sidebar grid by hand.
  // AD-90b: các callback dưới đây phải ổn định giữa những lần vẽ lại do ĐỒNG HỒ
  // (mỗi giây) — nếu không, React.memo của lưới câu hỏi/thẻ câu hỏi mất tác dụng.
  const goToNextUnanswered = useCallback(() => {
    if (!data) return;
    const n = data.total;
    for (let step = 1; step <= n; step++) {
      const i = (current + step) % n;
      if (!answers[data.questions[i].id]) { setCurrent(i); return; }
    }
  }, [data, answers, current]);

  // Submitting is final — confirm via an IN-PAGE modal (không dùng confirm() gốc
  // của Windows: trong kiosk nó là cửa sổ riêng → kẹt + làm lớp chặn phím tạm ngưng).
  const confirmSubmit = useCallback(() => setSubmitOpen(true), []);
  const goPrev = useCallback(() => setCurrent((c) => c - 1), []);
  const goNext = useCallback(() => setCurrent((c) => c + 1), []);

  if (!data) return <div className="min-h-screen flex items-center justify-center text-slate-500">Đang tải đề…</div>;

  const answeredCount = data.questions.filter((x) => answers[x.id]).length;
  const unansweredCount = data.total - answeredCount;

  return (
    <div className="h-screen flex flex-col bg-slate-100 overflow-hidden">
      {/* AD-88: mất đồng bộ kéo dài = bài làm CHỈ nằm trên máy này — máy hỏng là mất.
          Phải la to để thí sinh/giám thị xử lý từ sớm, không phải cuối giờ mới biết. */}
      {saveStatus === "disconnected" && (
        <div className="bg-red-600 text-white text-center text-sm font-semibold px-4 py-2">
          ⚠️ MẤT KẾT NỐI MÁY CHỦ — bài làm chưa được đồng bộ, KHÔNG tự ý đổi máy.
          Cứ làm tiếp và <u>giơ tay báo giám thị</u> kiểm tra mạng máy này.
        </div>
      )}
      <header className="bg-white border-b px-4 py-2 flex items-center justify-between">
        <span className="font-medium text-slate-800 text-base">{candidate?.full_name}</span>
        <div className="flex items-center gap-4">
          <SaveIndicator status={saveStatus} />
          <Timer seconds={secondsLeft} />
          <button
            onClick={() => setNotesOpen((o) => !o)}
            title="Giấy nháp (theo từng câu)"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition ${
              notesOpen ? "bg-amber-500 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            <NotebookPen size={16} /> Giấy nháp
          </button>
          <button
            onClick={() => setCalcOpen((o) => !o)}
            title="Máy tính khoa học"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition ${
              calcOpen ? "bg-blue-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            <Calculator size={16} /> Máy tính
          </button>
          <button
            onClick={() => setRefOpen((o) => !o)}
            title="Bảng tham chiếu xét nghiệm"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition ${
              refOpen ? "bg-teal-600 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
            }`}
          >
            <FlaskConical size={16} /> Tham chiếu XN
          </button>
          {/* Ảnh thí sinh — góc trên bên phải, phóng to để giám thị đối chiếu dễ. */}
          {candidate?.photo_path && (
            <img src={photoUrl(candidate.photo_path)}
              className="w-16 h-20 object-cover rounded-lg border-2 border-slate-300 bg-slate-100 shrink-0" />
          )}
        </div>
      </header>

      {tabCount > 3 && (
        <div className="bg-red-600 text-white text-sm px-4 py-1 flex items-center gap-2">
          <AlertTriangle size={16} /> Cảnh báo: bạn đã chuyển tab/cửa sổ {tabCount} lần. Hành vi này được ghi lại.
        </div>
      )}

      <div className="flex-1 flex overflow-hidden">
        <QuestionNavigator
          questions={data.questions}
          answers={answers}
          current={current}
          total={data.total}
          answeredCount={answeredCount}
          unansweredCount={unansweredCount}
          onSelect={setCurrent}
          onJumpUnanswered={goToNextUnanswered}
        />

        {/* Main — scrolls independently of the (tall) navigator; the question is
            vertically centered so it stays in view without scrolling the page. */}
        <main className="flex-1 overflow-auto p-6 flex flex-col">
          <QuestionCard
            q={data.questions[current]}
            index={current}
            total={data.total}
            answers={answers}
            unansweredCount={unansweredCount}
            onSelect={selectOption}
            onPrev={goPrev}
            onNext={goNext}
            onJumpUnanswered={goToNextUnanswered}
            onSubmit={confirmSubmit}
          />
        </main>

        {/* Giấy nháp theo từng câu — panel phải, toggled từ header (lưu cục bộ) */}
        <QuestionNotes
          open={notesOpen}
          onClose={() => setNotesOpen(false)}
          sessionId={sessionId}
          questionId={data.questions[current].id}
          questionNumber={current + 1}
        />

        {/* Scientific calculator — fixed right-side panel, toggled from header */}
        <ScientificCalculator open={calcOpen} onClose={() => setCalcOpen(false)} />

        {/* Bảng tham chiếu xét nghiệm — panel phải, toggled từ header (dữ liệu tĩnh) */}
        <LabReference open={refOpen} onClose={() => setRefOpen(false)} />
      </div>

      {/* Time-up overlay — the candidate's own clock hit 0; the server auto-submits
          + scores within a few seconds, then the result screen appears (AD-47). */}
      {timeUp && (
        <Overlay icon={<Hourglass size={32} className="text-blue-600" />} iconBg="bg-blue-100"
          title="Đã hết giờ làm bài">
          Bài làm của bạn đã được khoá và đang được <b>nộp + chấm tự động</b>. Vui lòng
          <b> giữ nguyên màn hình</b> trong giây lát. KHÔNG tắt máy.
        </Overlay>
      )}

      {/* Pause overlay — this candidate's clock was frozen by a giám thị/chủ tịch (AD-47). */}
      {paused && (
        <Overlay icon={<Pause size={32} className="text-amber-600" />} iconBg="bg-amber-100"
          title="Bài thi của bạn đang tạm dừng"
          footer={<>Còn lại: <span className="font-mono">{secondsLeft != null ? `${Math.floor(secondsLeft / 60).toString().padStart(2, "0")}:${(secondsLeft % 60).toString().padStart(2, "0")}` : "—"}</span></>}>
          Giám thị đã tạm dừng bài thi của bạn. Đồng hồ đã ngừng — thời gian làm bài được giữ nguyên.
          Vui lòng chờ đến khi giám thị cho tiếp tục.
        </Overlay>
      )}

      {/* AD-90: nộp bài KHÔNG lên được server — báo rõ + cho bấm lại (trước đây
          lỗi bị nuốt im lặng, thí sinh tưởng đã nộp mà server vẫn "đang làm"). */}
      {submitError && (
        <ConfirmOverlay
          title="Chưa nộp được bài!"
          confirmText="Thử nộp lại"
          onCancel={clearSubmitError}
          onConfirm={() => { clearSubmitError(); doSubmit(false); }}
        >
          <span className="text-rose-700 font-semibold">{submitError}</span>
        </ConfirmOverlay>
      )}

      {/* Xác nhận nộp bài — modal TRONG TRANG (không dùng confirm() gốc) */}
      {submitOpen && (
        <ConfirmOverlay
          title="Nộp bài thi?"
          confirmText="Nộp bài"
          onCancel={() => setSubmitOpen(false)}
          onConfirm={() => { setSubmitOpen(false); doSubmit(false); }}
        >
          {unansweredCount > 0 ? (
            <>Bạn còn <b className="text-rose-600">{unansweredCount}</b> câu chưa trả lời. Sau khi nộp <b>KHÔNG thể sửa lại</b>.</>
          ) : (
            <>Bạn chắc chắn muốn nộp bài? Sau khi nộp <b>KHÔNG thể sửa lại</b>.</>
          )}
        </ConfirmOverlay>
      )}
    </div>
  );
}

function ConfirmOverlay({ title, children, confirmText, onConfirm, onCancel }: {
  title: string; children: React.ReactNode; confirmText: string;
  onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/80 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-2xl p-7 max-w-sm w-[90%] text-center">
        <h2 className="text-xl font-bold text-slate-800">{title}</h2>
        <p className="text-sm text-slate-600 mt-2">{children}</p>
        <div className="flex gap-3 mt-6">
          <button onClick={onCancel}
            className="flex-1 py-2.5 rounded-lg border border-slate-300 text-slate-700 font-medium hover:bg-slate-50">
            Để sau
          </button>
          <button onClick={onConfirm}
            className="flex-1 py-2.5 rounded-lg bg-blue-600 text-white font-semibold hover:bg-blue-700">
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}

function Overlay({ icon, iconBg, title, children, footer }: {
  icon: React.ReactNode; iconBg: string; title: string;
  children: React.ReactNode; footer?: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/90 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow-2xl p-8 max-w-sm text-center">
        <div className={`mx-auto w-16 h-16 rounded-full ${iconBg} flex items-center justify-center mb-4`}>{icon}</div>
        <h2 className="text-xl font-bold text-slate-800">{title}</h2>
        <p className="text-sm text-slate-600 mt-2">{children}</p>
        {footer && <p className="text-xs text-slate-400 mt-4">{footer}</p>}
      </div>
    </div>
  );
}

function Timer({ seconds }: { seconds: number | null }) {
  if (seconds == null) return null;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  const danger = seconds < 300;
  return (
    <span className={`font-mono text-lg font-bold ${danger ? "text-red-600" : "text-slate-800"}`}>
      {String(m).padStart(2, "0")}:{String(s).padStart(2, "0")}
    </span>
  );
}

function SaveIndicator({ status }: { status: SaveStatus }) {
  const map = {
    saved: { icon: <Wifi size={16} />, text: "Đã lưu", cls: "text-green-600" },
    saving: { icon: <Wifi size={16} />, text: "Đang lưu…", cls: "text-amber-500" },
    disconnected: { icon: <WifiOff size={16} />, text: "Mất kết nối — báo giám thị", cls: "text-red-600 font-semibold" },
  }[status];
  return <span className={`flex items-center gap-1 text-xs ${map.cls}`}>{map.icon} {map.text}</span>;
}
