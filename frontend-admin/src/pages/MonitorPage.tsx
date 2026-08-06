import { useMemo, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Wifi } from "lucide-react";
import { sittingsApi } from "../api/sittings";
import { monitorApi, type SessionSummary } from "../api/monitor";
import { errorMessage } from "../api/client";
import type { Sitting } from "../api/types";
import StatusBadge from "../components/StatusBadge";
import ExamCountdown from "../components/ExamCountdown";
import DisconnectAlerts from "../components/DisconnectAlerts";
import StuckPausedAlerts from "../components/StuckPausedAlerts";
import SessionTable from "./monitor/SessionTable";
import StatFilters from "./monitor/StatFilters";
import StartExamControls from "./monitor/StartExamControls";
import type { Filter, DisplayRow } from "./monitor/constants";

interface Ctx { examId: string; sittingId: string; sitting: Sitting }

export default function MonitorPage() {
  const qc = useQueryClient();
  const { sittingId, sitting } = useOutletContext<Ctx>();
  const selectedId = sittingId;

  const { data: sessions = [] } = useQuery({
    queryKey: ["sessions", selectedId],
    queryFn: () => sittingsApi.sessions(selectedId),
    enabled: !!selectedId,
    refetchInterval: 8000,
  });
  const { data: roster } = useQuery({
    queryKey: ["roster", selectedId],
    queryFn: () => sittingsApi.roster(selectedId),
    enabled: !!selectedId,
    refetchInterval: 15000,
  });

  // Mất kết nối: gom lên hộp cảnh báo đầu trang. Nhãn vẫn còn ở từng dòng, nhưng
  // bảng vài trăm dòng thì phải cuộn mới thấy (phản ánh 02-08).
  const offlineRows = useMemo(
    () => sessions.filter((s: SessionSummary) => s.offline).map((s: SessionSummary) => ({
      key: s.session_id, full_name: s.full_name, cccd: s.cccd,
      room_name: s.room_name, last_seen_seconds: s.last_seen_seconds,
    })),
    [sessions],
  );
  // Tạm dừng mà đã quá giờ: vòng quét tự nộp bỏ qua họ nên bài treo mãi (AD-121 #2).
  const stuckRows = useMemo(
    () => sessions.filter((s: SessionSummary) => s.overdue_paused).map((s: SessionSummary) => ({
      key: s.session_id, full_name: s.full_name, cccd: s.cccd, room_name: s.room_name,
    })),
    [sessions],
  );

  const [filter, setFilter] = useState<Filter>("all");

  const [toast, setToast] = useState<{ text: string; kind: "ok" | "info" | "err" } | null>(null);
  const flash = (text: string, kind: "ok" | "info" | "err" = "ok") => {
    setToast({ text, kind });
    setTimeout(() => setToast(null), 4000);
  };
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["sessions", selectedId] });
    qc.invalidateQueries({ queryKey: ["roster", selectedId] });
    qc.invalidateQueries({ queryKey: ["sitting", selectedId] });
  };
  const ctrl = (
    fn: () => Promise<any>,
    after?: (r: any) => string,
    confirmMsg?: string,
  ) => async () => {
    if (confirmMsg && !confirm(confirmMsg)) return;
    try {
      const r = await fn();
      invalidate();
      if (after) flash(after(r), "ok");
    } catch (e) {
      flash(errorMessage(e, "Thao tác thất bại"), "err");
    }
  };
  const start = useMutation({ mutationFn: () => sittingsApi.start(selectedId) });
  const logoutCand = useMutation({
    mutationFn: (id: string) => monitorApi.logout(id),
    onSuccess: () => { invalidate(); flash("Đã đăng xuất thí sinh — có thể đăng nhập lại ở máy khác."); },
  });
  const admitCand = useMutation({
    mutationFn: (id: string) => monitorApi.admit(id),
    onSuccess: () => { invalidate(); flash("Đã duyệt thí sinh vào thi — màn hình của họ sẽ vào đề trong giây lát."); },
  });
  const pauseCand = useMutation({
    mutationFn: (id: string) => monitorApi.pauseSession(id),
    onSuccess: () => { invalidate(); flash("⏸ Đã tạm dừng bài thi của thí sinh."); },
    onError: () => flash("Tạm dừng thất bại.", "err"),
  });
  const resumeCand = useMutation({
    mutationFn: (id: string) => monitorApi.resumeSession(id),
    onSuccess: () => { invalidate(); flash("▶ Đã tiếp tục bài thi của thí sinh."); },
    onError: () => flash("Tiếp tục thất bại.", "err"),
  });
  const extendCand = useMutation({
    mutationFn: ({ id, minutes }: { id: string; minutes: number }) =>
      monitorApi.extendSession(id, minutes),
    onSuccess: (_r, v) => { invalidate(); flash(`⏱ Đã cộng ${v.minutes} phút cho thí sinh này.`); },
    onError: (e) => flash(errorMessage(e, "Cộng giờ thất bại"), "err"),
  });
  const terminateCand = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      monitorApi.terminateSession(id, reason),
    onSuccess: () => { invalidate(); flash("⛔ Đã đình chỉ thi — bài được chấm với phần đã làm."); },
    onError: (e) => flash(errorMessage(e, "Đình chỉ thất bại"), "err"),
  });
  const pauseAll = useMutation({ mutationFn: () => sittingsApi.pauseAll(selectedId) });
  const resumeAll = useMutation({ mutationFn: () => sittingsApi.resumeAll(selectedId) });

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const s of sessions) c[s.status] = (c[s.status] ?? 0) + 1;
    return c;
  }, [sessions]);

  const pending = roster?.not_logged_in ?? [];
  const sessionRows: DisplayRow[] = sessions.map((s) => ({ kind: "session", s }));
  const pendingRows: DisplayRow[] = pending.map((c) => ({ kind: "pending", c }));
  const displayRows: DisplayRow[] =
    filter === "all" ? [...sessionRows, ...pendingRows]
    : filter === "logged_in" ? sessionRows
    : filter === "not_logged_in" ? pendingRows
    // "Đã nộp" gộp cả timeout (hết-giờ-tự-nộp) — khớp với box.
    : filter === "submitted"
      ? sessionRows.filter((r) => r.kind === "session" && (r.s.status === "submitted" || r.s.status === "timeout"))
    : sessionRows.filter((r) => r.kind === "session" && r.s.status === filter);

  const isActive = sitting.status === "active";
  const hasExam = sitting.has_payload;
  const hasRunning = sessions.some((s) => s.status === "in_progress");
  const anyPaused = sessions.some((s) => s.paused);
  const hasFinished = sessions.some((s) => s.status === "submitted" || s.status === "timeout");
  const examOver = hasFinished && !hasRunning;
  const readyCount = counts.ready ?? 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
          Giám sát <Wifi size={16} className="text-green-500" />
        </h2>
        <div className="flex items-center gap-3">
          <ExamCountdown endTime={roster?.earliest_end_time ?? null}
            lastEndTime={roster?.latest_end_time ?? null}
            serverTime={roster?.server_time ?? null} />
          <StatusBadge status={sitting.status} hasRunningSessions={hasRunning} />
        </div>
      </div>

      {offlineRows.length > 0 && (
        <div className="mb-3"><DisconnectAlerts rows={offlineRows} /></div>
      )}

      {stuckRows.length > 0 && (
        <div className="mb-3"><StuckPausedAlerts rows={stuckRows} /></div>
      )}

      {!isActive && (
        <p className="mb-3 text-sm bg-slate-50 text-slate-700 border border-slate-200 px-3 py-2 rounded">
          {sitting.status === "draft"
            ? <>Buổi thi chưa mở. {hasExam ? "Bấm \"Mở buổi\" ở phần đầu trang để bắt đầu." : "Hãy nạp đề (tab Đề thi) rồi mở buổi."}</>
            : "Buổi thi đã đóng — chỉ xem kết quả, không thao tác được nữa."}
        </p>
      )}

      {isActive && !hasExam && (
        <div className="mb-3 text-sm bg-amber-50 text-amber-800 border border-amber-200 px-3 py-2 rounded">
          ⚠️ Buổi thi chưa có đề. Vào tab <strong>Đề thi</strong> để nạp file QTI trước khi bắt đầu thi.
        </div>
      )}

      {isActive && (
        <StartExamControls
          sessions={sessions}
          hasExam={hasExam}
          hasRunning={hasRunning}
          anyPaused={anyPaused}
          examOver={examOver}
          readyCount={readyCount}
          onStart={(skip, missing) => ctrl(
            () => start.mutateAsync(),
            (r) => r.started
              ? `▶ Đã bắt đầu thi cho ${r.started} thí sinh.${skip ? " (bỏ qua kiểm tra tải đề)" : " Đồng hồ đang chạy."}`
              : "ℹ️ Chưa có thí sinh nào xác nhận thông tin.",
            skip
              ? `⚠️ CÒN ${missing} MÁY CHƯA TẢI XONG ĐỀ.\n\nCác máy đó có thể bị chậm/thiếu hình lúc đầu giờ. Chỉ nên bỏ qua khi máy đó đã hỏng/không dùng.\n\nVẫn BẮT ĐẦU THI ngay?`
              : "Bạn có chắc muốn BẮT ĐẦU THI?\n\nMọi máy đã tải đủ đề. Đồng hồ sẽ chạy cho tất cả thí sinh sẵn sàng; mỗi thí sinh có đồng hồ riêng và tự nộp khi hết giờ.",
          )()}
          onPauseAll={ctrl(() => pauseAll.mutateAsync(),
            (r) => `⏸ Đã tạm dừng ${r.paused} thí sinh.`,
            "Tạm dừng CẢ BUỔI?\n\nĐồng hồ mọi thí sinh đang làm bài sẽ dừng cho tới khi bạn bấm Tiếp tục.")}
          onResumeAll={ctrl(() => resumeAll.mutateAsync(),
            (r) => `▶ Đã tiếp tục ${r.resumed} thí sinh.`,
            "Tiếp tục CẢ BUỔI cho mọi thí sinh đang tạm dừng?")}
        />
      )}

      {toast && (
        <div className={`mb-4 px-3 py-2 rounded text-sm ${
          toast.kind === "ok" ? "bg-green-50 border border-green-200 text-green-800"
          : toast.kind === "err" ? "bg-rose-50 border border-rose-200 text-rose-800"
          : "bg-blue-50 border border-blue-200 text-blue-800"
        }`}>
          {toast.text}
        </div>
      )}

      <StatFilters
        counts={counts}
        assignedTotal={roster?.assigned_total ?? 0}
        loggedIn={roster?.logged_in ?? sessions.length}
        notLoggedIn={roster?.not_logged_in_total ?? pending.length}
        filter={filter}
        setFilter={setFilter}
      />

      <SessionTable
        rows={displayRows}
        hasRunning={hasRunning}
        onLogout={(s: SessionSummary) => { if (confirm(`Đăng xuất "${s.full_name}"?\n\nThí sinh sẽ bị thoát khỏi máy đang dùng. Họ có thể đăng nhập lại ở máy khác. (Nếu đang làm bài, đáp án đã lưu được giữ lại để làm tiếp.)`)) logoutCand.mutate(s.session_id); }}
        onAdmit={(s: SessionSummary) => { if (confirm(`Duyệt "${s.full_name}" vào thi?\n\nThí sinh đi trễ sẽ vào làm bài NGAY. Màn hình của họ tự vào đề sau vài giây.`)) admitCand.mutate(s.session_id); }}
        onPause={(s: SessionSummary) => pauseCand.mutate(s.session_id)}
        onResume={(s: SessionSummary) => resumeCand.mutate(s.session_id)}
        onExtend={(s: SessionSummary) => {
          const raw = prompt(`Cộng thêm bao nhiêu phút cho "${s.full_name}"?\n\n`
            + "Chỉ thí sinh này được thêm giờ — cả phòng không đổi.", "10");
          if (raw === null) return;
          const minutes = Number(raw.trim());
          if (!Number.isInteger(minutes) || minutes < 1 || minutes > 180) {
            flash("Số phút phải là số nguyên từ 1 đến 180.", "err");
            return;
          }
          extendCand.mutate({ id: s.session_id, minutes });
        }}
        onTerminate={(s: SessionSummary) => {
          const reason = prompt(`ĐÌNH CHỈ THI "${s.full_name}"?\n\n`
            + "Bài sẽ dừng hẳn và được chấm với những gì đã làm. Không hoàn tác được.\n\n"
            + "Nhập lý do (bắt buộc, sẽ lưu vào nhật ký):", "");
          if (reason === null) return;
          if (reason.trim().length < 3) {
            flash("Phải ghi lý do đình chỉ (ít nhất 3 ký tự).", "err");
            return;
          }
          terminateCand.mutate({ id: s.session_id, reason: reason.trim() });
        }}
      />
    </div>
  );
}
