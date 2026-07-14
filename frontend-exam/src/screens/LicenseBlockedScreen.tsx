import { ShieldX } from "lucide-react";

/** Giấy phép server hết hạn/thiếu (AD-74) — backend trả 403 license_* cho mọi
 * API. Thí sinh chỉ cần biết "hệ thống tạm ngưng, gọi giám thị"; gate vẫn poll
 * /status nên khi quản trị nhập key mới, màn đăng nhập tự hiện lại. */
export default function LicenseBlockedScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-lg p-8 text-center">
        <div className="mx-auto w-16 h-16 rounded-full bg-rose-100 flex items-center justify-center mb-4">
          <ShieldX size={32} className="text-rose-500" />
        </div>
        <h1 className="text-xl font-bold text-slate-800">Hệ thống tạm ngưng hoạt động</h1>
        <p className="text-sm text-slate-600 mt-2">
          Vui lòng báo giám thị / cán bộ phụ trách. Hệ thống sẽ hoạt động trở lại
          ngay sau khi được kích hoạt — không cần làm gì trên máy này.
        </p>
      </div>
    </div>
  );
}
