import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, ShieldAlert, ShieldX } from "lucide-react";
import { licenseApi } from "../api/license";
import { errorMessage } from "../api/client";
import { useAuthStore } from "../stores/auth";

// Trang Giấy phép server (AD-74, AD-81). Cài xong TỰ dùng thử 90 ngày (không cần
// key); nhập key ở đây để GIA HẠN. Mọi vai trò XEM được trạng thái (endpoint GET
// nằm trong skip-list nên hết hạn vẫn vào được); chỉ super_admin nhập key.
// Interceptor 403 license_* (api/client.ts) tự đẩy người dùng về đây khi bị khoá.

const STATUS_UI: Record<string, { label: string; cls: string }> = {
  valid: { label: "Đang hoạt động", cls: "bg-emerald-50 border-emerald-200 text-emerald-800" },
  trial: { label: "Đang dùng thử", cls: "bg-sky-50 border-sky-200 text-sky-800" },
  expired: { label: "ĐÃ HẾT HẠN", cls: "bg-rose-50 border-rose-200 text-rose-800" },
  missing: { label: "CHƯA CÓ GIẤY PHÉP", cls: "bg-rose-50 border-rose-200 text-rose-800" },
  clock_tampered: {
    label: "ĐỒNG HỒ HỆ THỐNG BẤT THƯỜNG",
    cls: "bg-rose-50 border-rose-200 text-rose-800",
  },
};

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("vi-VN", {
    day: "2-digit", month: "2-digit", year: "numeric",
  });
}

export default function LicensePage() {
  const admin = useAuthStore((s) => s.admin);
  const isSuper = admin?.role === "super_admin";
  const qc = useQueryClient();
  const [key, setKey] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const { data, isLoading } = useQuery({ queryKey: ["license"], queryFn: licenseApi.get });

  const activate = useMutation({
    mutationFn: (k: string) => licenseApi.set(k),
    onSuccess: (info) => {
      setMessage({ ok: true, text: `Đã gia hạn — hết hạn ${fmtDate(info.expires_at)}.` });
      setKey("");
      qc.invalidateQueries({ queryKey: ["license"] });
    },
    onError: (err) => setMessage({ ok: false, text: errorMessage(err, "Gia hạn thất bại") }),
  });

  if (isLoading) return <p className="text-slate-500">Đang tải…</p>;
  const status = data?.status ?? "missing";
  const ui = STATUS_UI[status] ?? STATUS_UI.missing;
  const ok = status === "valid" || status === "trial";
  const isTrial = status === "trial";

  return (
    <div className="max-w-2xl space-y-5">
      <h1 className="text-xl font-bold text-slate-800">Giấy phép sử dụng</h1>

      <div className={`border rounded-xl p-5 ${ui.cls}`}>
        <div className="flex items-center gap-3">
          {ok ? <BadgeCheck size={28} /> : status === "clock_tampered" ? <ShieldAlert size={28} /> : <ShieldX size={28} />}
          <div>
            <p className="font-bold text-lg">{ui.label}</p>
            {data?.issued_to && <p className="text-sm">Cấp cho: <b>{data.issued_to}</b></p>}
          </div>
        </div>
        {data?.expires_at && (
          <p className="mt-3 text-sm">
            {isTrial ? "Dùng thử tới: " : "Hết hạn: "}<b>{fmtDate(data.expires_at)}</b>
            {ok && data.days_left != null && <> — còn <b>{data.days_left}</b> ngày</>}
          </p>
        )}
        {isTrial && (
          <p className="mt-2 text-sm">
            Bản dùng thử tự động 90 ngày kể từ lúc cài. Nhập <b>key gia hạn</b> bên dưới bất cứ
            lúc nào để kéo dài thời gian sử dụng.
          </p>
        )}
        {ok && data?.warn && (
          <p className="mt-2 text-sm font-semibold text-amber-700">
            ⚠️ Sắp hết hạn — liên hệ nhà cung cấp để lấy key gia hạn ngay từ bây giờ.
          </p>
        )}
        {!ok && (
          <p className="mt-3 text-sm">
            Toàn bộ chức năng thi đang bị khoá. Dữ liệu (kết quả, thí sinh, báo cáo) vẫn
            được giữ nguyên và mở lại ngay khi nhập key gia hạn hợp lệ.
          </p>
        )}
      </div>

      {isSuper ? (
        <form
          className="bg-white border border-slate-200 rounded-xl p-5 space-y-3"
          onSubmit={(e) => { e.preventDefault(); setMessage(null); activate.mutate(key.trim()); }}
        >
          <p className="font-semibold text-slate-700">Nhập key gia hạn</p>
          <textarea
            className="input font-mono text-xs h-28 w-full"
            placeholder="EXAM-…"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          {message && (
            <p className={`text-sm ${message.ok ? "text-emerald-700" : "text-rose-700"}`}>{message.text}</p>
          )}
          <button
            type="submit"
            disabled={!key.trim() || activate.isPending}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm disabled:opacity-50"
          >
            {activate.isPending ? "Đang gia hạn…" : "Gia hạn"}
          </button>
        </form>
      ) : (
        !ok && (
          <p className="text-sm text-slate-600">
            Liên hệ <b>Quản trị hệ thống</b> (tài khoản Quản trị) để nhập key gia hạn.
          </p>
        )
      )}
    </div>
  );
}
