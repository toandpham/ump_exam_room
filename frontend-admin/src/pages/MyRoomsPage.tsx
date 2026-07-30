import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { DoorOpen, Pause, Play } from "lucide-react";
import { roomsApi } from "../api/rooms";
import type { MyRoom } from "../api/types";
import { sittingsApi } from "../api/sittings";
import { monitorApi, type SessionSummary } from "../api/monitor";
import ExamCountdown from "../components/ExamCountdown";
import { STATUS_LABEL } from "./monitor/constants";
import { offlineLabel } from "../lib/offline";

type RoomFilter = "all" | "logged_in" | "not_logged_in" | "in_progress" | "submitted";

export default function MyRoomsPage() {
  const { data: rooms = [], isLoading } = useQuery({
    queryKey: ["my-rooms"], queryFn: roomsApi.myRooms, refetchInterval: 8000,
  });

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
        <DoorOpen size={22} /> Phòng của tôi
      </h1>
      <p className="text-sm text-slate-500 -mt-3">
        Theo dõi thí sinh phòng bạn và <strong>tạm dừng / tiếp tục</strong> bài của từng em khi cần.
        (Thí sinh do chủ tịch chia phòng sẵn.)
      </p>

      {isLoading && <p className="text-slate-400">Đang tải…</p>}
      {!isLoading && rooms.length === 0 && (
        <p className="text-slate-400">Bạn chưa được phân công phòng thi nào.</p>
      )}
      {rooms.map((room) => <RoomBlock key={room.room_id} room={room} />)}
    </div>
  );
}

function RoomBlock({ room }: { room: MyRoom }) {
  const qc = useQueryClient();
  const sittingId = room.active_sitting_id;
  const { data: seats = [], isLoading: seatsLoading } = useQuery({
    queryKey: ["room-seating", room.room_id],
    queryFn: () => roomsApi.roomSeating(room.room_id),
    refetchInterval: 15000,
  });
  const { data: sessions = [] } = useQuery({
    queryKey: ["sessions", sittingId],
    queryFn: () => sittingsApi.sessions(sittingId!),
    enabled: !!sittingId,
    refetchInterval: 8000,
  });

  const invalidateSessions = () => qc.invalidateQueries({ queryKey: ["sessions", sittingId] });
  const pause = useMutation({ mutationFn: (id: string) => monitorApi.pauseSession(id), onSuccess: invalidateSessions });
  const resume = useMutation({ mutationFn: (id: string) => monitorApi.resumeSession(id), onSuccess: invalidateSessions });

  const [filter, setFilter] = useState<RoomFilter>("all");

  // Merge the room roster with live session status by candidate.
  const sessByCand = new Map(sessions.map((s: SessionSummary) => [s.candidate_id, s]));
  const seatedAll = [...seats].sort((a, b) => a.full_name.localeCompare(b.full_name));
  const matchesFilter = (candidateId: string): boolean => {
    const s = sessByCand.get(candidateId);
    switch (filter) {
      case "logged_in": return s !== undefined && s.status !== "absent";
      case "not_logged_in": return s === undefined;
      case "in_progress": return s?.status === "in_progress";
      case "submitted": return s?.status === "submitted" || s?.status === "timeout";
      default: return true;
    }
  };
  const seated = seatedAll.filter((c) => matchesFilter(c.candidate_id));

  // Per-room stats computed from the FULL room roster (không theo bộ lọc đang chọn).
  const stats = {
    registered: seatedAll.length,
    loggedIn: seatedAll.filter(c => {
      const s = sessByCand.get(c.candidate_id);
      return s !== undefined && s.status !== "absent";
    }).length,
    notLoggedIn: seatedAll.filter(c => !sessByCand.has(c.candidate_id)).length,
    inProgress: seatedAll.filter(c => sessByCand.get(c.candidate_id)?.status === "in_progress").length,
    submitted: seatedAll.filter(c => {
      const st = sessByCand.get(c.candidate_id)?.status;
      return st === "submitted" || st === "timeout";
    }).length,
  };

  // Mỗi box vừa hiển thị số, vừa là bộ lọc bảng bên dưới (bấm lại box đang chọn để bỏ lọc).
  const statBoxes: { key: RoomFilter; label: string; value: number; colorClass: string }[] = [
    { key: "all", label: "Đăng ký", value: stats.registered, colorClass: "text-slate-800" },
    { key: "logged_in", label: "Đã đăng nhập", value: stats.loggedIn, colorClass: "text-blue-700" },
    { key: "not_logged_in", label: "Chưa đăng nhập", value: stats.notLoggedIn, colorClass: "text-slate-500" },
    { key: "in_progress", label: "Đang làm", value: stats.inProgress, colorClass: "text-green-700" },
    { key: "submitted", label: "Đã nộp", value: stats.submitted, colorClass: "text-violet-700" },
  ];

  return (
    <div className="bg-white rounded-xl shadow-sm p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div>
          <h2 className="font-semibold text-slate-800">{room.room_name}</h2>
          <span className="text-xs text-slate-500">{room.exam_name} · {room.candidate_count} thí sinh</span>
        </div>
        <div className="flex items-center gap-2">
          {/* AD-124: nút "Thêm thí sinh" đã GỠ — giám thị chỉ Tạm dừng / Tiếp tục
              bài thi; danh sách dự thi là trách nhiệm của chủ tịch. */}
          <ExamCountdown endTime={room.cohort_end_time} serverTime={room.server_time} />
        </div>
      </div>

      {/* Per-room stat boxes (clickable filters) */}
      <div className="grid grid-cols-3 sm:grid-cols-5 gap-2 mb-3">
        {statBoxes.map(({ key, label, value, colorClass }) => {
          const active = filter === key;
          return (
            <button key={key} type="button"
              onClick={() => setFilter(active && key !== "all" ? "all" : key)}
              title={active && key !== "all" ? "Bấm lại để bỏ lọc" : `Lọc: ${label}`}
              className={`rounded-lg p-2 text-center transition ${
                active ? "bg-blue-600 text-white ring-2 ring-blue-300" : "bg-slate-50 hover:bg-slate-100"
              }`}>
              <p className={`text-[10px] leading-tight ${active ? "text-white/80" : "text-slate-500"}`}>{label}</p>
              <p className={`text-lg font-bold ${active ? "text-white" : colorClass}`}>{value}</p>
            </button>
          );
        })}
      </div>


      {seatsLoading ? (
        <p className="text-sm text-slate-400">Đang tải…</p>
      ) : seatedAll.length === 0 ? (
        <p className="text-sm text-slate-400">Phòng chưa có thí sinh (chủ tịch chia phòng trước).</p>
      ) : seated.length === 0 ? (
        <p className="text-sm text-slate-400">Không có thí sinh nào khớp bộ lọc.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-left">
              <tr>
                <th className="px-3 py-2 w-12 text-center">STT</th>
                <th className="px-3 py-2">Họ tên</th>
                <th className="px-3 py-2">CCCD / Hộ chiếu</th>
                <th className="px-3 py-2">Ngày sinh</th>
                <th className="px-3 py-2">Đơn vị</th>
                <th className="px-3 py-2">Trạng thái</th>
                <th className="px-3 py-2 text-right"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {seated.map((row, idx) => {
                const s = sessByCand.get(row.candidate_id);
                const isAbsent = s?.status === "absent";
                return (
                  <tr key={row.candidate_id} className="hover:bg-slate-50">
                    <td className="px-3 py-2 text-center text-slate-400">{idx + 1}</td>
                    <td className="px-3 py-2">
                      {row.full_name}
                      {s?.paused && (
                        <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">tạm dừng</span>
                      )}
                      {isAbsent && (
                        <span className="ml-2 text-xs px-1.5 py-0.5 rounded bg-rose-100 text-rose-700">Vắng</span>
                      )}
                      {s?.offline && (
                        <span title="Máy này đã ngừng gọi về máy chủ — kiểm tra mạng/máy của thí sinh"
                          className="ml-2 text-xs px-1.5 py-0.5 rounded bg-slate-700 text-white font-semibold">
                          ⚡ {offlineLabel(s.last_seen_seconds)}
                        </span>
                      )}
                      {row.info_disputed && (
                        <span title="Thí sinh báo thông tin cá nhân bị sai — sửa lại giúp thí sinh"
                          className="ml-2 text-xs px-1.5 py-0.5 rounded bg-rose-100 text-rose-700 font-semibold">
                          ⚠ Báo sai thông tin
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 font-mono">
                      {row.cccd}
                      {row.id_type === "passport" && (
                        <span className="ml-1.5 px-1 py-0.5 rounded bg-amber-100 text-amber-700 text-[10px] font-sans align-middle">HC</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-slate-600">{row.birth_date ?? "—"}</td>
                    <td className="px-3 py-2 text-slate-600">{row.unit || "—"}</td>
                    <td className="px-3 py-2 text-slate-600">
                      {s ? (STATUS_LABEL[s.status] || s.status) : <span className="text-slate-400">chưa đăng nhập</span>}
                    </td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      {s?.status === "in_progress" && (
                        s.paused ? (
                          <button
                            onClick={() => resume.mutate(s.session_id)}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded border border-green-300 bg-green-50 hover:bg-green-100 text-xs text-green-700"
                          >
                            <Play size={14} /> Tiếp tục
                          </button>
                        ) : (
                          <button
                            onClick={() => pause.mutate(s.session_id)}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded border border-amber-300 bg-amber-50 hover:bg-amber-100 text-xs text-amber-700"
                          >
                            <Pause size={14} /> Tạm dừng
                          </button>
                        )
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
