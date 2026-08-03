import { WifiOff } from "lucide-react";
import { offlineLabel } from "../lib/offline";

export interface DisconnectedRow {
  key: string;
  full_name: string;
  cccd: string;
  room_name?: string | null;
  last_seen_seconds: number | null;
}

/** Hộp cảnh báo MẤT KẾT NỐI, đặt trên đầu màn giám sát.
 *
 * Vì sao cần: nhãn "mất kết nối" nằm trong từng dòng thí sinh nên với bảng vài trăm
 * dòng phải cuộn mới thấy — người vận hành 02-08 báo dễ bỏ sót. Hộp này gom tất cả
 * lên trên.
 *
 * Đây là danh sách SỐNG dựng từ trạng thái hiện tại, KHÔNG phải dòng sự kiện: máy
 * kết nối lại là tự biến mất, không cần bấm bỏ qua. Cố ý chỉ báo mất kết nối — hộp
 * thông báo tổng hợp cũ đã bị gỡ vì gây rối (AD-77). */
export default function DisconnectAlerts({ rows }: { rows: DisconnectedRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="rounded-xl border-2 border-red-300 bg-red-50 p-3">
      <p className="flex items-center gap-2 font-bold text-red-800">
        <WifiOff size={18} />
        {rows.length} thí sinh đang MẤT KẾT NỐI
      </p>
      <p className="text-xs text-red-700/80 mt-0.5">
        Máy đã ngừng gọi về máy chủ trên 90 giây — kiểm tra mạng hoặc máy của các em này.
        Bài làm đã lưu vẫn còn; đăng nhập lại là làm tiếp được.
      </p>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {rows.map((r) => (
          <li key={r.key}
            className="rounded-lg bg-white border border-red-200 px-2 py-1 text-xs text-red-900">
            <span className="font-semibold">{r.full_name}</span>
            <span className="font-mono text-red-700/70"> · {r.cccd}</span>
            {r.room_name && <span className="text-red-700/70"> · {r.room_name}</span>}
            <span className="text-red-600"> · {offlineLabel(r.last_seen_seconds)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
