import { api } from "./client";
import type { Candidate, Exam } from "../store";

export interface LoginResponse {
  token: string | null;
  candidate: Candidate;
  exam: Exam;
  requires_takeover?: boolean;
}

export interface ActiveExamSummary {
  id: string;
  name: string;
  exam_date: string | null;
  duration_minutes: number;
  allow_registration: boolean;
}

export interface ExamRunningStatus {
  open: boolean;
  exam_name: string | null;
  allow_registration: boolean;
}

export interface RegisterPayload {
  cccd: string;
  full_name: string;
  birth_date: string;       // YYYY-MM-DD
  unit: string;
  category: string;
  attempt_number: number;
  graduation_year?: number | null;
  major?: string | null;
  exam_id?: string | null;
}

export interface SessionState {
  session_id: string | null;
  status: string | null;
  submitted_at: string | null;
  time_remaining_seconds: number | null;
  paused: boolean;
  started_at: string | null;   // SP-2c: mốc bắt đầu chung (null nếu chưa có)
  server_time: string;          // SP-2c: giờ server lúc trả state (bù lệch đồng hồ máy con)
}

export interface ExamOption {
  id: string;
  text: string;
  images: string[];
}
export interface ExamQuestion {
  id: string;
  text: string;
  images: string[];
  options: ExamOption[];
}
export interface QuestionsResponse {
  status: string;
  time_remaining_seconds: number | null;
  total: number;
  answers: Record<string, string>;
  questions: ExamQuestion[];
}

export const examApi = {
  login: async (cccd: string, force = false): Promise<LoginResponse> =>
    (await api.post("/exam/auth/login", { cccd, force })).data,
  activeExams: async (): Promise<ActiveExamSummary[]> =>
    (await api.get("/exam/auth/active-exams")).data,
  status: async (): Promise<ExamRunningStatus> =>
    (await api.get("/exam/auth/status")).data,
  register: async (payload: RegisterPayload): Promise<LoginResponse> =>
    (await api.post("/exam/auth/register", payload)).data,
  confirm: async (): Promise<SessionState> => (await api.post("/exam/auth/confirm")).data,
  dispute: async () => (await api.post("/exam/auth/dispute")).data,
  me: async (): Promise<LoginResponse> => (await api.get("/exam/me")).data,
  state: async (): Promise<SessionState> => (await api.get("/exam/state")).data,
  questions: async (): Promise<QuestionsResponse> => (await api.get("/exam/questions")).data,
  answer: async (question_id: string, selected_option: string | null) =>
    (await api.post("/exam/answer", { question_id, selected_option })).data,
  // AD-69: đẩy đáp án theo LÔ (giảm số request xuống server).
  answersBulk: async (answers: { question_id: string; selected_option: string | null }[]) =>
    (await api.post("/exam/answers", { answers })).data,
  submit: async () => (await api.post("/exam/submit")).data,
  result: async (): Promise<{ status: string; submitted_at: string | null; total: number; answered: number; total_correct: number }> =>
    (await api.get("/exam/result")).data,
};
