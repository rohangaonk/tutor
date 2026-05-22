export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Hardcoded until auth is built (Phase 6 step 1)
export const USER_ID = "550e8400-e29b-41d4-a716-446655440000";

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
  const res = await fetch(`${API_BASE}/documents/${USER_ID}`);
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
  const res = await fetch(`${API_BASE}/upload/presign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, content_type: contentType, user_id: USER_ID }),
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
  const res = await fetch(`${API_BASE}/upload/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, s3_key: s3Key, user_id: USER_ID }),
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

export async function getQuizReport(sessionId: string): Promise<QuizReport> {
  const res = await fetch(`${API_BASE}/quiz/${sessionId}/report`);
  if (!res.ok) throw new Error(`Report fetch failed: ${res.statusText}`);
  return res.json();
}

export async function startQuiz(
  docId: string,
  maxQuestions = 5
): Promise<QuizStartResponse> {
  const res = await fetch(`${API_BASE}/quiz/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId, user_id: USER_ID, max_questions: maxQuestions }),
  });
  if (!res.ok) throw new Error(`Quiz start failed: ${res.statusText}`);
  return res.json();
}

export async function submitAnswer(
  sessionId: string,
  answer: string
): Promise<QuizAnswerResponse> {
  const res = await fetch(`${API_BASE}/quiz/answer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, answer }),
  });
  if (!res.ok) throw new Error(`Quiz answer failed: ${res.statusText}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Chat (streaming)
// ---------------------------------------------------------------------------

export async function* streamChat(
  question: string,
  documentId: string
): AsyncGenerator<string> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      document_id: documentId,
      user_id: USER_ID,
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
