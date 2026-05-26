export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------------------------------------------------------------------------
// Auth token helpers (stored in localStorage)
// ---------------------------------------------------------------------------

const TOKEN_KEY = "tutor_token";
const EMAIL_KEY = "tutor_email";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string, email: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(EMAIL_KEY, email);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
}

export function getStoredEmail(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(EMAIL_KEY);
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Authenticated fetch — clears token and redirects to /login on 401. */
async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const res = await fetch(url, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers as Record<string, string> | undefined) },
  });
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  }
  return res;
}

export async function signup(email: string, password: string): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(err.detail ?? "Signup failed");
  }
}

export async function signin(email: string, password: string): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/signin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as { detail?: string };
    throw new Error(err.detail ?? "Sign in failed");
  }
  const data = await res.json() as { access_token: string };
  setToken(data.access_token, email);
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Document {
  id: string;
  name: string;
  status: "pending" | "processing" | "ready" | "failed";
  created_at: string;
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export async function listDocuments(): Promise<Document[]> {
  const res = await apiFetch(`${API_BASE}/documents`);
  if (!res.ok) throw new Error(`Failed to list documents: ${res.statusText}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Upload
// ---------------------------------------------------------------------------

export async function presignUpload(
  filename: string,
  contentType: string
): Promise<{ presigned_url: string; s3_key: string }> {
  const res = await apiFetch(`${API_BASE}/upload/presign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, content_type: contentType }),
  });
  if (!res.ok) throw new Error(`Presign failed: ${res.statusText}`);
  return res.json();
}

export async function uploadToS3(
  presignedUrl: string,
  file: File
): Promise<void> {
  const res = await fetch(presignedUrl, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });
  if (!res.ok) throw new Error(`S3 upload failed: ${res.status}`);
}

export async function confirmUpload(
  filename: string,
  s3Key: string
): Promise<{ document_id: string }> {
  const res = await apiFetch(`${API_BASE}/upload/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, s3_key: s3Key }),
  });
  if (!res.ok) throw new Error(`Confirm failed: ${res.statusText}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Chat (streaming)
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Quiz
// ---------------------------------------------------------------------------

export interface QuizStartResponse {
  session_id: string;
  question: string;
  concept: string;
  difficulty: string;
}

export interface QuizAnswerResponse {
  feedback: string;
  correct_answer: string;
  confidence_score: number;
  is_correct: boolean;
  next_question: string | null;
  next_concept: string | null;
  difficulty: string;
  is_completed: boolean;
}

export interface QuizReportConcept {
  concept: string;
  total: number;
  correct: number;
  accuracy: number;
  avg_confidence: number;
}

export interface QuizReport {
  session_id: string;
  concepts: QuizReportConcept[];
}

export interface QuizSession {
  session_id: string;
  doc_id: string;
  doc_name: string;
  created_at: string;
  score: number;
  questions_asked: number;
  completed: boolean;
}

export async function listQuizSessions(): Promise<QuizSession[]> {
  const res = await apiFetch(`${API_BASE}/quiz/sessions`);
  if (!res.ok) throw new Error(`Sessions fetch failed: ${res.statusText}`);
  return res.json();
}

export interface QuizAttempt {
  id: string;
  question: string;
  user_answer: string;
  correct: boolean;
  concept: string | null;
  ai_feedback: string | null;
  confidence_score: number;
  difficulty_level: string | null;
}

export async function listQuizAttempts(sessionId: string): Promise<QuizAttempt[]> {
  const res = await apiFetch(`${API_BASE}/quiz/${sessionId}/attempts`);
  if (!res.ok) throw new Error(`Attempts fetch failed: ${res.statusText}`);
  return res.json();
}

export async function getQuizReport(sessionId: string): Promise<QuizReport> {
  const res = await apiFetch(`${API_BASE}/quiz/${sessionId}/report`);
  if (!res.ok) throw new Error(`Report fetch failed: ${res.statusText}`);
  return res.json();
}

export async function startQuiz(
  docId: string,
  maxQuestions = 5
): Promise<QuizStartResponse> {
  const res = await apiFetch(`${API_BASE}/quiz/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId, max_questions: maxQuestions }),
  });
  if (!res.ok) throw new Error(`Quiz start failed: ${res.statusText}`);
  return res.json();
}

export async function submitAnswer(
  sessionId: string,
  answer: string,
  signal?: AbortSignal
): Promise<QuizAnswerResponse> {
  const res = await apiFetch(`${API_BASE}/quiz/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, answer }),
    signal,
  });
  if (!res.ok) throw new Error(`Quiz answer failed: ${res.statusText}`);
  return res.json();
}

export async function skipQuestion(
  sessionId: string,
  questionsAsked: number
): Promise<QuizAnswerResponse> {
  const res = await apiFetch(`${API_BASE}/quiz/skip`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, questions_asked: questionsAsked }),
  });
  if (!res.ok) throw new Error(`Quiz skip failed: ${res.statusText}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Progress
// ---------------------------------------------------------------------------

export interface TopicStrength {
  topic: string;
  strength_score: number;
  updated_at: string;
}

export interface DocumentProgress {
  doc_id: string;
  doc_name: string;
  sessions_completed: number;
  avg_session_score: number;
  topics: TopicStrength[];
}

export interface ProgressResponse {
  user_id: string;
  documents: DocumentProgress[];
  overall_strength: number;
}

export async function getProgress(): Promise<ProgressResponse> {
  const res = await apiFetch(`${API_BASE}/progress/me`);
  if (!res.ok) throw new Error(`Progress fetch failed: ${res.statusText}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Chat (streaming)
// ---------------------------------------------------------------------------

export async function* streamChat(
  question: string,
  documentId: string
): AsyncGenerator<string> {
  const res = await apiFetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      document_id: documentId,
    }),
  });

  if (!res.ok) throw new Error(`Chat request failed: ${res.statusText}`);
  if (!res.body) throw new Error("No response body");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const token = line.slice(6);
      if (token === "[DONE]") return;
      if (token.startsWith("[ERROR]")) throw new Error(token.slice(8));
      yield token;
    }
  }
}
