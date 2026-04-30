const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface InterviewSummary {
  id: string;
  company_name: string;
  role_title: string;
  status: string;
  created_at: string;
  bidi_started_at: string | null;
  bidi_ended_at: string | null;
}

export interface AnswerOut {
  id: string;
  transcript_text: string;
  duration_sec: number;
  user_audio_s3_key: string | null;
}

export interface QuestionOut {
  id: string;
  order_index: number;
  question_text: string;
  question_audio_s3_key: string | null;
  answer: AnswerOut | null;
}

export interface EvaluationOut {
  id: string;
  question_id: string | null;
  content_score: number;
  expression_score: number;
  voice_score: number;
  overall_score: number;
  overall_result: string;
  improvement_suggestion: string;
  ideal_answer: string | null;
}

export interface InterviewDetail {
  id: string;
  company_name: string;
  role_title: string;
  status: string;
  bidi_tokens_total: number;
  bidi_cost_usd: number;
  bidi_started_at: string | null;
  bidi_ended_at: string | null;
  created_at: string;
  questions: QuestionOut[];
  evaluations: EvaluationOut[];
}

export async function fetchInterviews(): Promise<InterviewSummary[]> {
  const res = await fetch(`${API_BASE}/api/interviews`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch interviews: ${res.status}`);
  return res.json();
}

export async function fetchInterview(id: string): Promise<InterviewDetail> {
  const res = await fetch(`${API_BASE}/api/interviews/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch interview ${id}: ${res.status}`);
  return res.json();
}

export async function fetchAudioUrl(
  interviewId: string,
  questionId: string,
  role: "assistant" | "user"
): Promise<string> {
  const res = await fetch(
    `${API_BASE}/api/interviews/${interviewId}/questions/${questionId}/audio?role=${role}`,
    { cache: "no-store" }
  );
  if (!res.ok) throw new Error(`No audio: ${res.status}`);
  const data: { url: string } = await res.json();
  return data.url;
}
