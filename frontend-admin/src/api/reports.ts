export interface ReportData {
  meta: {
    exam_name: string;
    sitting_name: string;
    exam_date: string | null;
    question_count: number;
  };
  rows: Array<{
    stt: number;
    cccd: string;
    ho_dem: string;
    ten: string;
    room_name: string | null;
    birth_date: string | null;
    score: number | null;
    total_correct: number | null;
    status: string;
    answers: string[];
  }>;
  questions: Array<{
    index: number;
    correct_option: string;
  }>;
}
