import { ShieldAlert } from "lucide-react";

export default function SebRequiredScreen() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-100 p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-lg p-8 text-center">
        <div className="mx-auto w-16 h-16 rounded-full bg-amber-100 flex items-center justify-center mb-4">
          <ShieldAlert size={32} className="text-amber-600" />
        </div>
        <h1 className="text-xl font-bold text-slate-800">Cần Safe Exam Browser</h1>
        <p className="text-sm text-slate-600 mt-2">
          Kỳ thi này chỉ làm được trong <strong>Safe Exam Browser</strong>. Vui lòng mở bài thi
          bằng phần mềm SEB trên máy thi (bấm shortcut do giám thị cài), hoặc báo giám thị nếu
          máy chưa được cấu hình.
        </p>
      </div>
    </div>
  );
}
