/** Giám thị thêm thí sinh lẻ (walk-in) thẳng vào phòng mình — AD-54.
 * Tách khỏi MyRoomsPage ở refactor đợt 3. */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { roomsApi } from "../../api/rooms";
import { errorMessage } from "../../api/client";
import Modal from "../../components/Modal";
import Field from "../../components/Field";

export default function AddCandidateModal({ roomId, roomName, onClose, onAdded }: {
  roomId: string; roomName: string; onClose: () => void; onAdded: () => void;
}) {
  const [idType, setIdType] = useState<"cccd" | "passport">("cccd");
  const [f, setF] = useState({
    cccd: "", full_name: "", birth_date: "", unit: "", category: "", attempt_number: 1,
  });
  const set = (k: keyof typeof f, v: string | number) => setF((s) => ({ ...s, [k]: v }));
  const idOk = idType === "cccd" ? /^\d{12}$/.test(f.cccd) : /^[A-Z0-9]{6,9}$/.test(f.cccd);
  const valid = idOk && f.full_name.trim() && f.birth_date && f.unit.trim() && f.category.trim();
  const add = useMutation({
    mutationFn: () => roomsApi.addRoomCandidate(roomId, f),
    onSuccess: () => { onAdded(); onClose(); },
  });

  return (
    <Modal open title={`Thêm thí sinh vào ${roomName}`} onClose={onClose}>
      <div className="space-y-3">
        <Field label="Giấy tờ tuỳ thân *">
          <div className="flex gap-1.5 mb-1.5">
            {([["cccd", "CCCD"], ["passport", "Hộ chiếu"]] as const).map(([t, l]) => (
              <button key={t} type="button" onClick={() => { setIdType(t); set("cccd", ""); }}
                className={`flex-1 py-1 rounded text-xs font-medium border ${
                  idType === t ? "bg-blue-600 text-white border-blue-600" : "bg-white text-slate-600 border-slate-300"
                }`}>{l}</button>
            ))}
          </div>
          <input className="input uppercase" inputMode={idType === "cccd" ? "numeric" : "text"} value={f.cccd} autoFocus
            placeholder={idType === "cccd" ? "12 chữ số" : "6–9 ký tự chữ/số"}
            onChange={(e) => set("cccd", idType === "cccd"
              ? e.target.value.replace(/\D/g, "").slice(0, 12)
              : e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 9))} />
        </Field>
        <Field label="Họ tên *">
          <input className="input" value={f.full_name} onChange={(e) => set("full_name", e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Ngày sinh *">
            <input type="date" className="input" value={f.birth_date} onChange={(e) => set("birth_date", e.target.value)} />
          </Field>
          <Field label="Lần dự thi">
            <input type="number" min={1} className="input" value={f.attempt_number}
              onChange={(e) => set("attempt_number", Math.max(1, Number(e.target.value) || 1))} />
          </Field>
        </div>
        <Field label="Đơn vị *">
          <input className="input" value={f.unit} onChange={(e) => set("unit", e.target.value)} />
        </Field>
        <Field label="Đối tượng *">
          <input className="input" value={f.category} onChange={(e) => set("category", e.target.value)} />
        </Field>
        {add.isError && <p className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded p-2">{errorMessage(add.error)}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border text-sm">Huỷ</button>
          <button disabled={!valid || add.isPending} onClick={() => add.mutate()}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm disabled:opacity-50">
            {add.isPending ? "Đang thêm…" : "Thêm vào phòng"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
