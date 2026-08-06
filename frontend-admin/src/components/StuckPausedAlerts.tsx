import { PauseCircle } from "lucide-react";

export interface StuckPausedRow {
  key: string;
  full_name: string;
  cccd: string;
  room_name?: string | null;
}

/** Hộp cảnh báo THÍ SINH TẠM DỪNG ĐÃ QUÁ GIỜ.
 *
 * Vì sao cần: vòng quét tự nộp cố ý bỏ qua phiên đang tạm dừng — không nộp thay
 * người đang bị dừng. Đúng, nhưng hệ quả là nếu không ai bấm Tiếp tục thì phiên nằm
 * đó mãi: không tự nộp, không hiện gì bất thường, và bảng vài trăm dòng thì chẳng
 * ai nhận ra (lỗ AD-121 #2).
 *
 * Danh sách SỐNG dựng từ trạng thái hiện tại — bấm Tiếp tục hoặc Đình chỉ là tự
 * biến mất, không cần bỏ qua thủ công. */
export default function StuckPausedAlerts({ rows }: { rows: StuckPausedRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="rounded-xl border-2 border-amber-400 bg-amber-50 p-3">
      <p className="flex items-center gap-2 font-bold text-amber-900">
        <PauseCircle size={18} />
        {rows.length} thí sinh đang TẠM DỪNG mà đã hết giờ
      </p>
      <p className="text-xs text-amber-800/80 mt-0.5">
        Các bài này sẽ không bao giờ tự nộp chừng nào còn tạm dừng. Hãy bấm{" "}
        <strong>Tiếp tục</strong> (trả lại đúng thời gian còn lại) hoặc xử lý dứt điểm
        trước khi đóng buổi.
      </p>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {rows.map((r) => (
          <li key={r.key}
            className="rounded-lg bg-white border border-amber-300 px-2 py-1 text-xs text-amber-900">
            <span className="font-semibold">{r.full_name}</span>
            <span className="font-mono text-amber-800/70"> · {r.cccd}</span>
            {r.room_name && <span className="text-amber-800/70"> · {r.room_name}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}
