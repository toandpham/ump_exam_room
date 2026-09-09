export type ExamStatus = "draft" | "active" | "closed";
export type SittingStatus = "draft" | "active" | "closed";

export interface Exam {
  id: string;
  name: string;
  description: string | null;
  duration_minutes: number;
  exam_date: string | null;
  status: ExamStatus;
  question_count: number;
  sitting_count: number;
  has_running_sessions: boolean;
  allow_registration: boolean;
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface Sitting {
  id: string;
  exam_id: string;
  name: string;
  description: string | null;
  scheduled_date: string | null;
  ordinal: number;
  duration_minutes: number;
  status: SittingStatus;
  shuffle_questions: boolean;
  shuffle_options: boolean;
  question_count: number;
  has_payload: boolean;
  has_running_sessions: boolean;
  created_at: string;
  updated_at: string;
}

export interface Room {
  id: string;
  exam_id: string;
  name: string;
  proctor_id: string | null;
  capacity: number;
  proctor_real_name: string | null;
  proctor_name: string | null;
  candidate_count: number;
}

export interface MyRoom {
  room_id: string;
  room_name: string;
  exam_id: string;
  exam_name: string;
  exam_status: string;
  active_sitting_id: string | null;
  candidate_count: number;
  cohort_end_time: string | null;   // đồng hồ thi chung (AD-78)
  server_time: string | null;
}

/** The `sitting` block returned inside a roster response (was `exam` before). */
export interface RosterSitting {
  sitting_id: string;
  exam_id: string;
  exam_name: string;
  sitting_name: string;
  exam_date: string | null;
  duration_minutes: number;
  status: string;
  question_count: number;
}

export interface Candidate {
  id: string;
  cccd: string;
  id_type?: string;   // 'cccd' | 'passport' (AD-58)
  full_name: string;
  birth_date: string;
  unit: string;
  photo_path: string | null;
  graduation_year: number | null;
  major: string | null;
  category: string;
  attempt_number: number;
  exam_id: string | null;
  exam_name: string | null;
  room_id: string | null;
  room_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export function uploadUrl(path: string | null | undefined): string | undefined {
  return path ? `/uploads/${path}` : undefined;
}
