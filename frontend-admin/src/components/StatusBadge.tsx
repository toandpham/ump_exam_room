import type { ExamStatus } from "../api/types";

const STYLES: Record<string, string> = {
  draft: "bg-slate-100 text-slate-700",
  open: "bg-blue-100 text-blue-800",       // active + chưa có ai làm bài
  active: "bg-green-100 text-green-800",   // active + đang có thí sinh thi
  closed: "bg-slate-200 text-slate-600",
};

const LABELS: Record<string, string> = {
  draft: "Nháp",
  open: "Đang mở",       // section sống — nhận đăng ký, link mọi action vô đây
  active: "Đang thi",    // đã có thí sinh làm bài
  closed: "Đã đóng",
};

export default function StatusBadge({
  status, hasRunningSessions,
}: { status: ExamStatus | string; hasRunningSessions?: boolean }) {
  // status='active' nghĩa là section đang sống (focus). Phân biệt 2 nhánh:
  //   - "Đang mở" — section sống, có thể nhận đăng ký, chưa ai làm bài
  //   - "Đang thi" — đã có ≥1 session in_progress (admin đã bấm Bắt đầu thi)
  const effective = status === "active" && !hasRunningSessions ? "open" : status;
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
      STYLES[effective] || "bg-slate-100 text-slate-700"
    }`}>
      {LABELS[effective] || effective}
    </span>
  );
}
