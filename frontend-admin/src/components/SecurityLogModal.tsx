import { useQuery } from "@tanstack/react-query";
import { candidatesApi } from "../api/candidates";
import Modal from "./Modal";

const LABELS: Record<string, string> = {
  login_attempt_invalid_cccd: "CCCD sai định dạng",
  login_attempt_not_in_whitelist: "Không trong danh sách",
  login_attempt_not_in_exam: "Không thuộc kỳ thi",
  login_rate_limited: "Quá nhiều lần thử",
};

export default function SecurityLogModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data = [], isLoading } = useQuery({
    queryKey: ["security-log"],
    queryFn: () => candidatesApi.failedLogins(200),
    enabled: open,
  });

  return (
    <Modal open={open} title="Nhật ký đăng nhập thất bại" onClose={onClose} width="max-w-2xl">
      {isLoading ? (
        <p className="text-slate-400">Đang tải…</p>
      ) : (
        <div className="max-h-[60vh] overflow-auto">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 sticky top-0 text-left">
              <tr>
                <th className="px-2 py-1">Thời gian</th>
                <th className="px-2 py-1">Loại</th>
                <th className="px-2 py-1">CCCD thử</th>
                <th className="px-2 py-1">IP</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((e) => (
                <tr key={e.id}>
                  <td className="px-2 py-1">{new Date(e.created_at).toLocaleString("vi-VN")}</td>
                  <td className="px-2 py-1">{LABELS[e.event_type] || e.event_type}</td>
                  <td className="px-2 py-1 font-mono">{e.cccd_attempted || "—"}</td>
                  <td className="px-2 py-1">{e.client_ip || "—"}</td>
                </tr>
              ))}
              {data.length === 0 && <tr><td colSpan={4} className="px-2 py-4 text-center text-slate-400">Chưa có sự kiện.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
