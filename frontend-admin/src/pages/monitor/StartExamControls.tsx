import { Pause, Play } from "lucide-react";
import type { SessionSummary } from "../../api/monitor";

/** Thanh điều khiển buổi thi: Bắt đầu thi (gate theo tiến độ tải đề, AD-110),
 * Tạm dừng/Tiếp tục cả buổi, và dòng gợi ý bước kế tiếp.
 * Tách khỏi MonitorPage ở refactor đợt 3 — thuần props, không tự gọi API. */
export default function StartExamControls({
  sessions, hasExam, hasRunning, anyPaused, examOver, readyCount,
  onStart, onPauseAll, onResumeAll,
}: {
  sessions: SessionSummary[];
  hasExam: boolean;
  hasRunning: boolean;
  anyPaused: boolean;
  examOver: boolean;
  readyCount: number;
  /** `skipPreloadCheck` = van an toàn: bỏ qua kiểm tra "đã tải đề". */
  onStart: (skipPreloadCheck: boolean, missing: number) => void;
  onPauseAll: () => void;
  onResumeAll: () => void;
}) {
  // AD-110: chỉ cho Bắt đầu thi khi MỌI máy sẵn sàng đã tải xong đề (máy thí sinh
  // tự báo về lúc chờ). Máy hỏng/tắt ngang không bao giờ báo → có đường
  // "bỏ qua kiểm tra" riêng (confirm cảnh báo) để 1 máy chết không kẹt cả phòng.
  const readySessions = sessions.filter((s) => s.status === "ready");
  const loadedCount = readySessions.filter((s) => s.preloaded).length;
  const allLoaded = readySessions.length > 0 && loadedCount >= readySessions.length;
  const missing = readySessions.length - loadedCount;
  const canStart = hasExam && readyCount > 0 && !examOver;

  return (
    <div className="flex gap-2 mb-4 flex-wrap items-center">
      <CtrlBtn
        onClick={() => onStart(false, 0)}
        disabled={!canStart || !allLoaded}
        icon={Play} label="Bắt đầu thi" green />

      {/* Van an toàn — máy hỏng/tắt ngang không bao giờ báo "đã tải đề", không có
          nút này thì 1 máy chết kẹt cả phòng. */}
      {canStart && !allLoaded && (
        <button
          onClick={() => onStart(true, missing)}
          className="text-xs text-amber-700 underline underline-offset-2 hover:text-amber-900"
          title="Chỉ dùng khi có máy hỏng không thể tải đề"
        >
          Vẫn bắt đầu (bỏ qua {missing} máy chưa tải đề)
        </button>
      )}

      {hasRunning && (anyPaused ? (
        <CtrlBtn onClick={onResumeAll} icon={Play} label="Tiếp tục cả buổi" green />
      ) : (
        <CtrlBtn onClick={onPauseAll} icon={Pause} label="Tạm dừng cả buổi" />
      ))}

      {examOver ? (
        <span className="text-xs text-slate-500">→ Đã có bài nộp. Xem <strong>Báo cáo</strong>, hoặc <strong>Đóng buổi</strong> ở đầu trang để lưu trữ.</span>
      ) : !hasExam ? (
        <span className="text-xs text-slate-500">→ Cần nạp đề trước</span>
      ) : hasRunning ? (
        <span className="text-xs text-green-700">→ Đang thi. Tạm dừng/Tiếp tục từng thí sinh ở bảng bên dưới.</span>
      ) : readyCount === 0 ? (
        <span className="text-xs text-slate-500">→ Đợi thí sinh đăng nhập + xác nhận</span>
      ) : !allLoaded ? (
        <span className="text-xs text-amber-700">→ Đã tải đề <strong>{loadedCount}/{readySessions.length}</strong> máy — chờ đủ mới bắt đầu được</span>
      ) : (
        // SP-2b: confirm → READY tự động, không cần bước phân phối thủ công.
        <span className="text-xs text-green-700">→ {readyCount} thí sinh sẵn sàng, <strong>đề đã tải đủ {loadedCount}/{readySessions.length} máy</strong> — bấm <strong>Bắt đầu thi</strong></span>
      )}
    </div>
  );
}

/** Giữ NGUYÊN style nút gốc của MonitorPage (chuyển nguyên khối, không đổi UI). */
function CtrlBtn({ onClick, disabled, icon: Icon, label, green }: {
  onClick: () => void; disabled?: boolean; icon: any; label: string; green?: boolean;
}) {
  const cls = green ? "bg-green-600 hover:bg-green-700" : "bg-blue-600 hover:bg-blue-700";
  return (
    <button onClick={onClick} disabled={disabled} className={`flex items-center gap-2 px-4 py-2 rounded-lg text-white text-sm disabled:opacity-50 ${cls}`}>
      <Icon size={16} /> {label}
    </button>
  );
}
