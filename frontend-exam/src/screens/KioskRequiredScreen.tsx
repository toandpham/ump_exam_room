import { MonitorSmartphone } from "lucide-react";

/** AD-91: thí sinh mở bài thi bằng trình duyệt thường (Firefox/Chrome/Edge…).
 * Máy chủ từ chối mọi API thi — màn này chỉ dẫn họ mở đúng phần mềm thi. */
export default function KioskRequiredScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-lg p-8 text-center">
        <div className="mx-auto w-16 h-16 rounded-full bg-amber-100 flex items-center justify-center mb-4">
          <MonitorSmartphone size={32} className="text-amber-600" />
        </div>
        <h1 className="text-xl font-bold text-slate-800">Phải thi bằng phần mềm thi</h1>
        <p className="text-sm text-slate-600 mt-3">
          Không được làm bài bằng trình duyệt. Vui lòng <strong>đóng cửa sổ này</strong> và mở
          ứng dụng <strong>Phòng thi UMP</strong> trên màn hình nền của máy.
        </p>
        <p className="text-sm text-slate-500 mt-3">
          Máy chưa có ứng dụng thi? <strong>Giơ tay báo giám thị.</strong>
        </p>
      </div>
    </div>
  );
}
