import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScrollText, RefreshCw, Search } from "lucide-react";
import { adminsApi } from "../api/admins";

type Tone = "ok" | "warn" | "danger" | "neutral";

// label + colour for every event type written to exam_events.
const EVENTS: Record<string, { label: string; tone: Tone }> = {
  login_success: { label: "Đăng nhập thành công", tone: "ok" },
  login_attempt_invalid_cccd: { label: "Đăng nhập: CCCD sai định dạng", tone: "warn" },
  login_attempt_not_in_whitelist: { label: "Đăng nhập: không trong danh sách", tone: "warn" },
  login_attempt_not_in_exam: { label: "Đăng nhập: không thuộc kỳ thi", tone: "warn" },
  login_rate_limited: { label: "Bị chặn — thử quá nhiều lần", tone: "danger" },
  same_machine_login: { label: "Cùng máy nhiều tài khoản", tone: "danger" },
  register_success: { label: "Đăng ký tại chỗ", tone: "neutral" },
  register_duplicate_cccd: { label: "Trùng CCCD khi đăng ký", tone: "danger" },
  info_dispute: { label: "Báo sai thông tin", tone: "warn" },
  tab_change: { label: "Chuyển tab / cửa sổ", tone: "warn" },
  start: { label: "Bắt đầu thi / thao tác giám thị", tone: "neutral" },
  distribute: { label: "Tự sẵn sàng (cũ)", tone: "neutral" },
  submit: { label: "Nộp bài", tone: "ok" },
  reset: { label: "Đăng xuất / reset (giám thị)", tone: "neutral" },
  proctor_logout: { label: "Giám thị đăng xuất thí sinh", tone: "neutral" },
  absent_mark: { label: "Đánh dấu vắng", tone: "warn" },
  exam_end: { label: "Kết thúc thi", tone: "neutral" },
  exam_purged: { label: "Xoá đề khỏi máy chủ", tone: "neutral" },
  result_sealed: { label: "Niêm phong kết quả", tone: "ok" },
  result_tampered: { label: "⚠ Kết quả bị can thiệp", tone: "danger" },
};

const TONE_CLS: Record<Tone, string> = {
  ok: "bg-green-100 text-green-700",
  warn: "bg-amber-100 text-amber-700",
  danger: "bg-rose-100 text-rose-700",
  neutral: "bg-slate-100 text-slate-600",
};

function summarize(meta: Record<string, unknown> | null): string {
  if (!meta) return "";
  const keys = ["full_name", "action", "reason", "count", "others", "blocked_other",
    "attempted_name", "existing_name", "minutes", "submitted", "admin"];
  const parts = keys.filter((k) => meta[k] != null && meta[k] !== "")
    .map((k) => `${k}: ${Array.isArray(meta[k]) ? (meta[k] as unknown[]).join(", ") : meta[k]}`);
  return parts.join("  ·  ");
}

export default function AuditLogPage() {
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const { data = [], isFetching, refetch } = useQuery({
    queryKey: ["audit", type, q],
    queryFn: () => adminsApi.audit({ event_type: type || undefined, q: q || undefined, limit: 500 }),
    refetchInterval: 15000,
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
          <ScrollText size={22} className="text-blue-600" /> Nhật ký hệ thống
        </h1>
        <button onClick={() => refetch()} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-800">
          <RefreshCw size={15} className={isFetching ? "animate-spin" : ""} /> Làm mới
        </button>
      </div>
      <p className="text-sm text-slate-500 mb-4">
        Toàn bộ sự kiện: đăng nhập, nộp bài, thao tác giám thị, cảnh báo bảo mật, niêm phong kết quả… (mới nhất ở trên).
      </p>

      <div className="flex flex-wrap items-center gap-3 mb-3">
        <select className="input max-w-xs" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="">Tất cả loại sự kiện</option>
          {Object.entries(EVENTS).map(([v, { label }]) => <option key={v} value={v}>{label}</option>)}
        </select>
        <div className="relative">
          <Search size={15} className="absolute left-2.5 top-2.5 text-slate-400" />
          <input className="input pl-8 w-56" placeholder="Tìm theo CCCD…" value={q}
            onChange={(e) => setQ(e.target.value.replace(/\D/g, ""))} inputMode="numeric" />
        </div>
        <span className="text-sm text-slate-400">{data.length} sự kiện</span>
      </div>

      <div className="bg-white rounded-xl shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-3 py-2 w-44">Thời gian</th>
              <th className="px-3 py-2">Sự kiện</th>
              <th className="px-3 py-2 w-36">CCCD</th>
              <th className="px-3 py-2 w-32">IP</th>
              <th className="px-3 py-2">Chi tiết</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.map((e) => {
              const meta = EVENTS[e.event_type] ?? { label: e.event_type, tone: "neutral" as Tone };
              return (
                <tr key={e.id} className="hover:bg-slate-50 align-top">
                  <td className="px-3 py-2 text-xs text-slate-500 whitespace-nowrap">
                    {new Date(e.created_at).toLocaleString("vi-VN")}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${TONE_CLS[meta.tone]}`}>
                      {meta.label}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{e.cccd_attempted || "—"}</td>
                  <td className="px-3 py-2 text-xs">{e.client_ip || "—"}</td>
                  <td className="px-3 py-2 text-xs text-slate-500">{summarize(e.metadata)}</td>
                </tr>
              );
            })}
            {data.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-10 text-center text-slate-400">Chưa có sự kiện nào khớp.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
