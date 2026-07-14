import { create } from "zustand";

export interface Candidate {
  id: string;
  cccd: string;
  id_type?: "cccd" | "passport";   // AD-58: CCCD hoặc Hộ chiếu (backend trả về)
  full_name: string;
  birth_date: string;
  unit: string;
  major: string | null;
  category: string;
  attempt_number: number;
  photo_path: string | null;
}

export interface Exam {
  id: string;
  name: string;
  duration_minutes: number;
  exam_date: string | null;
}

interface ExamState {
  token: string | null;
  candidate: Candidate | null;
  exam: Exam | null;
  login: (token: string, candidate: Candidate, exam: Exam) => void;
  setIdentity: (candidate: Candidate, exam: Exam | null) => void;
  logout: () => void;
}

export const useStore = create<ExamState>((set) => ({
  token: localStorage.getItem("exam_token"),
  candidate: null,
  exam: null,
  login: (token, candidate, exam) => {
    localStorage.setItem("exam_token", token);
    set({ token, candidate, exam });
  },
  // Restore the displayed identity from the server (/exam/me) after a reload —
  // the store keeps only the token, so candidate/exam are re-fetched, not cached.
  setIdentity: (candidate, exam) => set((s) => ({ candidate, exam: exam ?? s.exam })),
  logout: () => {
    localStorage.removeItem("exam_token");
    set({ token: null, candidate: null, exam: null });
  },
}));

export function photoUrl(path: string | null | undefined): string | undefined {
  return path ? `/uploads/${path}` : undefined;
}
