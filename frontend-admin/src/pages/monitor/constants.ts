import type { RosterCandidate, SessionSummary } from "../../api/monitor";

export const STATUS_LABEL: Record<string, string> = {
  waiting: "Chờ", ready: "Sẵn sàng", in_progress: "Đang làm", submitted: "Đã nộp", timeout: "Hết giờ",
  absent: "Vắng",
};

// Only the values StatFilters can actually set (the four meta filters plus the
// three status chips it renders).
export type Filter =
  | "all" | "logged_in" | "not_logged_in"
  | "ready" | "in_progress" | "submitted";

export type DisplayRow =
  | { kind: "session"; s: SessionSummary }
  | { kind: "pending"; c: RosterCandidate };
