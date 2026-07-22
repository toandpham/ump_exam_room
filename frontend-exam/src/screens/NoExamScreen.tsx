import { CalendarClock } from "lucide-react";

/** Shown when no exam is in progress (no active exam, or no buổi opened yet).
 * The gate keeps polling /status, so this auto-switches to the login form the
 * moment a buổi opens — candidates don't need to refresh (AD-61). */
export default function NoExamScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-lg p-8 text-center">
        <div className="mx-auto w-16 h-16 rounded-full bg-slate-100 flex items-center justify-center mb-4">
          <CalendarClock size={32} className="text-slate-400" />
        </div>
        <h1 className="text-xl font-bold text-slate-800">Chưa có kỳ thi nào đang diễn ra</h1>
        <p className="text-sm text-slate-600 mt-2">
          Vui lòng chờ giám thị mở buổi thi. Màn hình đăng nhập sẽ tự hiện ngay khi
          kỳ thi bắt đầu — bạn không cần làm gì thêm.
        </p>
        <div className="mt-5 inline-flex items-center gap-2 text-xs text-slate-400">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          Đang chờ tín hiệu mở thi…
        </div>
      </div>
    </div>
  );
}
