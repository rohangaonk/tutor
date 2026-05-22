"use client";

import { useEffect, useState } from "react";
import {
  Document,
  listDocuments,
  startQuiz,
  submitAnswer,
  getQuizReport,
  QuizAnswerResponse,
  QuizReport,
} from "@/lib/api";

type Phase = "pick" | "loading" | "question" | "feedback" | "done" | "error";

interface QuizState {
  sessionId: string;
  question: string;
  concept: string;
  difficulty: string;
  questionsAsked: number;
  maxQuestions: number;
}

interface FeedbackState {
  feedback: string;
  correctAnswer: string;
  confidence: number;
  isCorrect: boolean;
  nextQuestion: string | null;
  nextConcept: string | null;
  nextDifficulty: string;
}

const DIFFICULTY_COLOUR: Record<string, string> = {
  easy: "text-green-400",
  medium: "text-yellow-400",
  hard: "text-red-400",
};

export default function QuizPage() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [docsError, setDocsError] = useState<string | null>(null);

  const [phase, setPhase] = useState<Phase>("pick");
  const [error, setError] = useState<string | null>(null);

  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [maxQuestions, setMaxQuestions] = useState(5);

  const [quiz, setQuiz] = useState<QuizState | null>(null);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [feedback, setFeedback] = useState<FeedbackState | null>(null);
  const [report, setReport] = useState<QuizReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  // Completed session summary
  const [history, setHistory] = useState<
    { question: string; answer: string; isCorrect: boolean; feedback: string; correctAnswer: string }[]
  >([]);
  const [pendingAnswer, setPendingAnswer] = useState<string>("");

  useEffect(() => {
    listDocuments()
      .then((all) => setDocs(all.filter((d) => d.status === "ready")))
      .catch((e) => setDocsError(e.message));
  }, []);

  async function handleStart() {
    if (!selectedDocId) return;
    setPhase("loading");
    setError(null);
    setHistory([]);
    try {
      const res = await startQuiz(selectedDocId, maxQuestions);
      setQuiz({
        sessionId: res.session_id,
        question: res.question,
        concept: res.concept,
        difficulty: res.difficulty,
        questionsAsked: 0,
        maxQuestions,
      });
      setAnswer("");
      setFeedback(null);
      setPhase("question");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  }

  async function handleSubmit() {
    if (!quiz || !answer.trim() || submitting) return;
    setSubmitting(true);
    setPendingAnswer(answer.trim());
    try {
      const res: QuizAnswerResponse = await submitAnswer(quiz.sessionId, answer.trim());

      const fb: FeedbackState = {
        feedback: res.feedback,
        correctAnswer: res.correct_answer,
        confidence: res.confidence_score,
        isCorrect: res.is_correct,
        nextQuestion: res.next_question ?? null,
        nextConcept: res.next_concept ?? null,
        nextDifficulty: res.difficulty,
      };
      setFeedback(fb);

      setHistory((prev) => [
        ...prev,
        {
          question: quiz.question,
          answer: answer.trim(),
          isCorrect: res.is_correct,
          feedback: res.feedback,
          correctAnswer: res.correct_answer,
        },
      ]);

      if (res.is_completed) {
        setPhase("done");
        // Auto-fetch report
        if (quiz) {
          setReportLoading(true);
          getQuizReport(quiz.sessionId)
            .then(setReport)
            .catch(() => setReport(null))
            .finally(() => setReportLoading(false));
        }
      } else {
        setPhase("feedback");
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
    } finally {
      setSubmitting(false);
    }
  }

  function handleNext() {
    if (!quiz || !feedback) return;
    setQuiz({
      ...quiz,
      question: feedback.nextQuestion!,
      concept: feedback.nextConcept ?? "",
      difficulty: feedback.nextDifficulty,
      questionsAsked: quiz.questionsAsked + 1,
    });
    setAnswer("");
    setFeedback(null);
    setPendingAnswer("");
    setPhase("question");
  }

  function handleReset() {
    setPhase("pick");
    setQuiz(null);
    setFeedback(null);
    setReport(null);
    setAnswer("");
    setError(null);
    setHistory([]);
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col items-center py-12 px-4">
      <h1 className="text-3xl font-bold mb-8">Quiz</h1>

      {/* ── Document picker ── */}
      {phase === "pick" && (
        <div className="w-full max-w-md space-y-4">
          {docsError && (
            <p className="text-red-400 text-sm">{docsError}</p>
          )}

          <div>
            <label className="block text-sm text-gray-400 mb-1">Document</label>
            <select
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm"
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
            >
              <option value="">— select a document —</option>
              {docs.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Questions ({maxQuestions})
            </label>
            <input
              type="range"
              min={3}
              max={10}
              value={maxQuestions}
              onChange={(e) => setMaxQuestions(Number(e.target.value))}
              className="w-full"
            />
          </div>

          <button
            onClick={handleStart}
            disabled={!selectedDocId}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 rounded-lg py-2 font-medium transition-colors"
          >
            Start Quiz
          </button>
        </div>
      )}

      {/* ── Loading ── */}
      {phase === "loading" && (
        <p className="text-gray-400 animate-pulse">Generating first question…</p>
      )}

      {/* ── Question ── */}
      {phase === "question" && quiz && (
        <div className="w-full max-w-2xl space-y-5">
          <div className="flex justify-between text-xs text-gray-500">
            <span>
              Question {quiz.questionsAsked + 1} / {quiz.maxQuestions}
            </span>
            <span>
              Concept:{" "}
              <span className="text-gray-300">{quiz.concept || "—"}</span>
              {"  "}·{"  "}
              Difficulty:{" "}
              <span className={DIFFICULTY_COLOUR[quiz.difficulty] ?? "text-gray-300"}>
                {quiz.difficulty}
              </span>
            </span>
          </div>

          <div className="bg-gray-800 rounded-xl p-5 border border-gray-700 text-base leading-relaxed">
            {quiz.question}
          </div>

          <textarea
            rows={4}
            placeholder="Type your answer…"
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.ctrlKey) handleSubmit();
            }}
            className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-3 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />

          <button
            onClick={handleSubmit}
            disabled={!answer.trim() || submitting}
            className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 rounded-lg py-2 font-medium transition-colors"
          >
            {submitting ? "Evaluating…" : "Submit Answer"}
          </button>
          <p className="text-xs text-gray-600 text-center">Ctrl + Enter to submit</p>
        </div>
      )}

      {/* ── Feedback ── */}
      {phase === "feedback" && quiz && feedback && (
        <div className="w-full max-w-2xl space-y-5">
          <div className="bg-gray-800 rounded-xl p-5 border border-gray-700 space-y-3">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Your answer</p>
            <p className="text-sm text-gray-300 italic">{pendingAnswer}</p>
          </div>

          <div
            className={`rounded-xl p-5 border ${
              feedback.isCorrect
                ? "bg-green-900/30 border-green-700"
                : "bg-red-900/30 border-red-700"
            } space-y-2`}
          >
            <p className="font-semibold">
              {feedback.isCorrect ? "✓ Correct" : "✗ Incorrect"}
              <span className="ml-3 text-sm font-normal text-gray-400">
                confidence {Math.round(feedback.confidence * 100)}%
              </span>
            </p>
            <p className="text-sm text-gray-200 leading-relaxed">{feedback.feedback}</p>
            {feedback.correctAnswer && (
              <div className="mt-2 pt-2 border-t border-gray-600">
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Correct answer</p>
                <p className="text-sm text-blue-300 leading-relaxed">{feedback.correctAnswer}</p>
              </div>
            )}
          </div>

          <button
            onClick={handleNext}
            className="w-full bg-indigo-600 hover:bg-indigo-500 rounded-lg py-2 font-medium transition-colors"
          >
            Next Question →
          </button>
        </div>
      )}

      {/* ── Done ── */}
      {phase === "done" && feedback && (
        <div className="w-full max-w-2xl space-y-6">
          <div className="text-center">
            <p className="text-2xl font-bold mb-1">Quiz complete!</p>
            <p className="text-gray-400 text-sm">
              Final answer — confidence {Math.round(feedback.confidence * 100)}%
            </p>
          </div>

          {/* Last answer feedback */}
          <div
            className={`rounded-xl p-5 border ${
              feedback.isCorrect
                ? "bg-green-900/30 border-green-700"
                : "bg-red-900/30 border-red-700"
            } space-y-2`}
          >
            <p className="font-semibold">
              {feedback.isCorrect ? "✓ Correct" : "✗ Incorrect"}
            </p>
            <p className="text-sm text-gray-200 leading-relaxed">{feedback.feedback}</p>
            {feedback.correctAnswer && (
              <div className="mt-2 pt-2 border-t border-gray-600">
                <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Correct answer</p>
                <p className="text-sm text-blue-300 leading-relaxed">{feedback.correctAnswer}</p>
              </div>
            )}
          </div>

          {/* Per-concept report */}
          <div className="space-y-2">
            <p className="text-sm text-gray-500 uppercase tracking-wide">Performance by concept</p>
            {reportLoading && (
              <p className="text-gray-500 text-sm animate-pulse">Loading report…</p>
            )}
            {!reportLoading && report && report.concepts.length > 0 && (
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-700">
                    <th className="pb-2 pr-4 font-normal">Concept</th>
                    <th className="pb-2 pr-4 font-normal text-center">Correct</th>
                    <th className="pb-2 pr-4 font-normal text-center">Accuracy</th>
                    <th className="pb-2 font-normal text-center">Avg confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {report.concepts.map((c) => (
                    <tr key={c.concept} className="border-b border-gray-800">
                      <td className="py-2 pr-4 text-gray-200">{c.concept}</td>
                      <td className="py-2 pr-4 text-center">
                        {c.correct}/{c.total}
                      </td>
                      <td className="py-2 pr-4 text-center">
                        <span
                          className={
                            c.accuracy >= 0.7
                              ? "text-green-400"
                              : c.accuracy >= 0.4
                              ? "text-yellow-400"
                              : "text-red-400"
                          }
                        >
                          {Math.round(c.accuracy * 100)}%
                        </span>
                      </td>
                      <td className="py-2 text-center text-gray-300">
                        {Math.round(c.avg_confidence * 100)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {!reportLoading && report && report.concepts.length === 0 && (
              <p className="text-gray-500 text-sm">No concept data available.</p>
            )}
          </div>

          {/* History */}
          <div className="space-y-3">
            <p className="text-sm text-gray-500 uppercase tracking-wide">Session recap</p>
            {history.map((h, i) => (
              <div
                key={i}
                className={`rounded-lg p-4 border text-sm space-y-1 ${
                  h.isCorrect
                    ? "border-green-800 bg-green-900/20"
                    : "border-red-800 bg-red-900/20"
                }`}
              >
                <p className="text-gray-300 font-medium">Q{i + 1}: {h.question}</p>
                <p className="text-gray-400 italic">Your answer: {h.answer}</p>
                <p className="text-gray-300">{h.feedback}</p>
                {h.correctAnswer && (
                  <p className="text-blue-300 text-xs mt-1">
                    <span className="text-gray-500">Correct: </span>{h.correctAnswer}
                  </p>
                )}
              </div>
            ))}
          </div>

          <button
            onClick={handleReset}
            className="w-full bg-gray-700 hover:bg-gray-600 rounded-lg py-2 font-medium transition-colors"
          >
            Start another quiz
          </button>
        </div>
      )}

      {/* ── Error ── */}
      {phase === "error" && (
        <div className="w-full max-w-md space-y-4 text-center">
          <p className="text-red-400">{error}</p>
          <button
            onClick={handleReset}
            className="bg-gray-700 hover:bg-gray-600 rounded-lg px-6 py-2 font-medium transition-colors"
          >
            Try again
          </button>
        </div>
      )}
    </div>
  );
}
