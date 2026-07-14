import { useState } from "react";
import { useOutletContext } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, KeyRound, Plus, Trash2 } from "lucide-react";
import type { Exam, Room } from "../../api/types";
import { roomsApi, type RoomUpdate } from "../../api/rooms";
import { adminsApi } from "../../api/admins";
import { errorMessage } from "../../api/client";
import Modal from "../../components/Modal";

interface Ctx { examId: string; exam: Exam }

export default function RoomsTab() {
  const { examId } = useOutletContext<Ctx>();
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [msg, setMsg] = useState("");

  const { data: rooms = [], isLoading } = useQuery({
    queryKey: ["rooms", examId], queryFn: () => roomsApi.listRooms(examId), enabled: !!examId,
  });
  const { data: proctors = [] } = useQuery({
    queryKey: ["room-proctors"], queryFn: adminsApi.roomProctors,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["rooms", examId] });
    qc.invalidateQueries({ queryKey: ["candidates"] });
  };

  const createMut = useMutation({
    mutationFn: () => roomsApi.createRoom(examId, { name: newName }),
    onSuccess: () => { setCreateOpen(false); setNewName(""); invalidate(); },
    onError: (e) => setMsg(errorMessage(e)),
  });
  const updateMut = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: RoomUpdate }) =>
      roomsApi.updateRoom(id, patch),
    onSuccess: invalidate,
    onError: (e) => setMsg(errorMessage(e)),
  });
  const removeMut = useMutation({
    mutationFn: (id: string) => roomsApi.removeRoom(id),
    onSuccess: invalidate,
    onError: (e) => setMsg(errorMessage(e)),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-slate-800">Phòng thi & giám thị</h2>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => roomsApi.seatingXlsx(examId)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-white text-sm hover:bg-slate-50">
            <Download size={16} /> Danh sách phòng (Excel)
          </button>
          <button onClick={() => roomsApi.seatingPdf(examId)}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border bg-white text-sm hover:bg-slate-50">
            <FileText size={16} /> Danh sách phòng (PDF)
          </button>
          <button onClick={() => { setMsg(""); setCreateOpen(true); }}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 text-white text-sm hover:bg-blue-700">
            <Plus size={16} /> Thêm phòng
          </button>
        </div>
      </div>

      <p className="text-sm text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
        Thí sinh được <strong>tự động chia phòng theo cột "Phòng"</strong> trong file Excel khi nhập danh sách
        (tab Thí sinh). Phòng có tên mới trong file sẽ tự được tạo. Ở đây chỉ cần <strong>gán giám thị</strong> cho từng phòng.
      </p>

      {msg && <p className="text-sm bg-slate-50 border border-slate-200 text-slate-700 px-3 py-2 rounded">{msg}</p>}

      <div className="bg-white rounded-xl shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2">Tên phòng</th>
              <th className="px-4 py-2">Sức chứa</th>
              <th className="px-4 py-2">Giám thị phụ trách</th>
              <th className="px-4 py-2">Đã xếp</th>
              <th className="px-4 py-2 text-right">Thao tác</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && <tr><td colSpan={5} className="px-4 py-6 text-center text-slate-400">Đang tải…</td></tr>}
            {!isLoading && rooms.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-8 text-center text-slate-400">Chưa có phòng. Bấm <strong>Thêm phòng</strong>.</td></tr>
            )}
            {rooms.map((r) => (
              <RoomRow key={r.id} room={r} proctors={proctors}
                onUpdate={(patch) => updateMut.mutate({ id: r.id, patch })}
                onRemove={() => { if (confirm(`Xoá phòng "${r.name}"?`)) removeMut.mutate(r.id); }} />
            ))}
          </tbody>
        </table>
      </div>

      <Modal open={createOpen} title="Thêm phòng thi" onClose={() => { setCreateOpen(false); setNewName(""); }}>
        <form onSubmit={(e) => { e.preventDefault(); createMut.mutate(); }} className="space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1">Tên phòng *</label>
            <input className="input" value={newName} autoFocus placeholder="VD: Phòng A1"
              onChange={(e) => setNewName(e.target.value)} />
          </div>
          {createMut.isError && <p className="text-sm text-rose-700">{errorMessage(createMut.error)}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => { setCreateOpen(false); setNewName(""); }} className="px-4 py-2 rounded-lg border text-sm">Huỷ</button>
            <button type="submit" disabled={!newName || createMut.isPending}
              className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm disabled:opacity-50">
              {createMut.isPending ? "Đang tạo…" : "Tạo phòng"}
            </button>
          </div>
        </form>
      </Modal>

    </div>
  );
}

function RoomRow({ room, proctors, onUpdate, onRemove }: {
  room: Room;
  proctors: { id: string; username: string; full_name: string | null }[];
  onUpdate: (patch: RoomUpdate) => void;
  onRemove: () => void;
}) {
  const [cap, setCap] = useState(String(room.capacity));
  const [realName, setRealName] = useState(room.proctor_real_name ?? "");
  const [pinInfo, setPinInfo] = useState<{ pin: string; username: string; full_name: string | null } | null>(null);
  const resetPin = useMutation({
    mutationFn: () => adminsApi.resetRoomProctorPin(room.proctor_id!),
    onSuccess: (r) => setPinInfo(r),
  });
  return (
    <tr className="hover:bg-slate-50 align-top">
      <td className="px-4 py-3 font-medium text-slate-800">{room.name}</td>
      <td className="px-4 py-3">
        <input type="number" min={0} max={500} className="input w-20" value={cap}
          onChange={(e) => setCap(e.target.value)}
          onBlur={() => { const n = Math.max(0, Number(cap) || 0); if (n !== room.capacity) onUpdate({ capacity: n }); }} />
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2 flex-wrap">
          <select className="input max-w-56" value={room.proctor_id ?? ""}
            onChange={(e) => { setPinInfo(null); onUpdate({ proctor_id: e.target.value || null }); }}>
            <option value="">— Chưa phân công —</option>
            {proctors.map((p) => (
              <option key={p.id} value={p.id}>{p.full_name || p.username}</option>
            ))}
          </select>
          {room.proctor_id && (
            <button onClick={() => resetPin.mutate()} disabled={resetPin.isPending}
              className="inline-flex items-center gap-1 text-xs px-2 py-1.5 rounded border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 disabled:opacity-50">
              <KeyRound size={13} /> {resetPin.isPending ? "Đang đặt…" : "Đặt lại MK (6 số)"}
            </button>
          )}
        </div>
        {/* Real name of the human sitting this room for this exam (AD-49) —
            stored for audit; the account above is a shared fixed pool. */}
        <input className="input mt-1.5 max-w-56 text-sm" value={realName}
          placeholder="Tên giám thị thật (vd: Nguyễn Văn A)"
          onChange={(e) => setRealName(e.target.value)}
          onBlur={() => {
            const v = realName.trim();
            if (v !== (room.proctor_real_name ?? "")) onUpdate({ proctor_real_name: v });
          }} />
        {pinInfo && (
          <p className="mt-1.5 text-xs text-slate-600">
            <b>{pinInfo.full_name || pinInfo.username}</b> — đăng nhập <span className="font-mono">{pinInfo.username}</span>,
            mật khẩu <b className="font-mono text-base text-blue-700">{pinInfo.pin}</b> (báo 6 số này cho giám thị).
          </p>
        )}
      </td>
      <td className="px-4 py-3 text-slate-600">{room.candidate_count}{room.capacity > 0 && ` / ${room.capacity}`}</td>
      <td className="px-4 py-3 text-right">
        <button title="Xoá phòng" onClick={onRemove} className="p-1.5 rounded hover:bg-slate-100">
          <Trash2 size={16} className="text-red-600" />
        </button>
      </td>
    </tr>
  );
}
