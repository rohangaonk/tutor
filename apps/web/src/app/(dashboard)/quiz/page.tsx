"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Document,
  listDocuments,
  startQuiz,
  submitAnswer,
  skipQuestion,
  getQuizReport,
  listQuizSessions,
  listQuizAttempts,
  QuizAnswerResponse,
  QuizReport,
  QuizSession,
  QuizAttempt,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  CheckCircle2,
  XCircle,
  Trophy,
  ChevronDown,
  ChevronUp,
  Upload,
  Loader2,
  ArrowRight,
  RotateCcw,
  BookOpen,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

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

const DIFFICULTY_BADGE: Record<string, string> = {
  easy: "bg-green-500/10 text-green-600 border-green-500/20",
  medium: "bg-amber-500/10 text-amber-600 border-amber-500/20",
  hard: "bg-red-500/10 text-red-600 border-red-500/20",
};

function ScoreBadge({ score, className }: { score: number; className?: string }) {
  const pct = Math.round(score * 100);
  const color = pct >= 70 ? "text-green-600" : pct >= 40 ? "text-amber-600" : "text-red-600";
  return <span className={cn("font-semibold tabular-nums", color, className)}>{pct}%</span>;
}

export default function QuizPage() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [pastSessions, setPastSessions] = useState<QuizSession[]>([]);
  const [expandedSession, setExpandedSession] = useState<string | null>(null);
  const [sessionReports, setSessionReports] = useState<Record<string, QuizReport>>({});
  const [sessionAttempts, setSessionAttempts] = useState<Record<string, QuizAttempt[]>>({});
  const [expandedAttempt, setExpandedAttempt] = useState<string | null>(null);

  const [phase, setPhase] = useState<Phase>("pick");
  const [error, setError] = useState<string | null>(null);
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [maxQuestions, setMaxQuestions] = useState(5);

  const [quiz, setQuiz] = useState<QuizState | null>(null);
  const [answer, setAnswer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [feedback, setFeedback] = useState<FeedbackState | null>(null);
  const [report, setReport] = useState<QuizReport | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [pendingAnswer, setPendingAnswer] = useState("");
  const [history, setHistory] = useState<
    { question: string; answer: string; isCorrect: boolean; feedback: string; correctAnswer: string }[]
  >([]);

  useEffect(() => {
    listDocuments()
      .then((all) => setDocs(all.filter((d) => d.status === "ready")))
      .catch((e) => toast.error(e.message))
      .finally(() => setDocsLoading(false));
    listQuizSessions()
      .then((all) => setPastSessions(all.filter((s) => s.completed)))
      .catch(() => {});
  }, []);

  async function handleExpandSession(sessionId: string) {
    if (expandedSession === sessionId) { setExpandedSession(null); return; }
    setExpandedSession(sessionId);
    setExpandedAttempt(null);
    const fetches: Promise<void>[] = [];
    if (!sessionReports[sessionId]) {
      fetches.push(getQuizReport(sessionId).then((r) => setSessionReports((p) => ({ ...p, [sessionId]: r }))).catch(() => {}));
    }
    if (!sessionAttempts[sessionId]) {
      fetches.push(listQuizAttempts(sessionId).then((a) => setSessionAttempts((p) => ({ ...p, [sessionId]: a }))).catch(() => {}));
    }
    await Promise.all(fetches);
  }

  async function handleStart() {
    if (!selectedDocId) return;
    // Clear any in-flight state from a previous quiz
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    setPhase("loading");
    setError(null);
    setHistory([]);
    try {
      const res = await startQuiz(selectedDocId, maxQuestions);
      setQuiz({ sessionId: res.session_id, question: res.question, concept: res.concept, difficulty: res.difficulty, questionsAsked: 0, maxQuestions });
      setAnswer("");
      setFeedback(null);
      setPhase("question");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
      toast.error("Failed to start quiz");
    }
  }

  async function handleSubmit() {
    if (!quiz || !answer.trim() || submitting) return;
    setSubmitting(true);
    setTimedOut(false);
    setPendingAnswer(answer.trim());

    const ac = new AbortController();
    abortControllerRef.current = ac;
    timerRef.current = setTimeout(() => setTimedOut(true), 7000);

    try {
      const res: QuizAnswerResponse = await submitAnswer(quiz.sessionId, answer.trim(), ac.signal);
      if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
      setTimedOut(false);
      abortControllerRef.current = null;

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
      setHistory((prev) => [...prev, { question: quiz.question, answer: answer.trim(), isCorrect: res.is_correct, feedback: res.feedback, correctAnswer: res.correct_answer }]);
      if (res.is_completed) {
        setPhase("done");
        setReportLoading(true);
        getQuizReport(quiz.sessionId).then(setReport).catch(() => setReport(null)).finally(() => setReportLoading(false));
      } else {
        setPhase("feedback");
      }
      setSubmitting(false);
    } catch (e) {
      if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
      abortControllerRef.current = null;
      if (e instanceof DOMException && e.name === "AbortError") {
        // User clicked Skip — handleSkip is taking over, don't reset state here
        console.log("[handleSubmit] aborted by skip");
        return;
      }
      setSubmitting(false);
      setTimedOut(false);
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
      toast.error("Failed to submit answer");
    }
  }

  function handleWait() {
    setTimedOut(false);
    timerRef.current = setTimeout(() => setTimedOut(true), 7000);
  }

  async function handleSkip() {
    if (!quiz) return;
    console.log("[handleSkip] called", { sessionId: quiz.sessionId, questionsAsked: quiz.questionsAsked, submitting, timedOut });
    // Abort any in-flight submit
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    setTimedOut(false);
    setSubmitting(true);
    try {
      console.log("[handleSkip] calling skipQuestion...");
      const res = await skipQuestion(quiz.sessionId, quiz.questionsAsked);
      console.log("[handleSkip] response", res);
      if (res.is_completed) {
        // Skipped the last question — go straight to done
        setFeedback({
          feedback: "",
          correctAnswer: "",
          confidence: 0,
          isCorrect: false,
          nextQuestion: null,
          nextConcept: null,
          nextDifficulty: res.difficulty,
        });
        setPhase("done");
        setReportLoading(true);
        getQuizReport(quiz.sessionId).then(setReport).catch(() => setReport(null)).finally(() => setReportLoading(false));
      } else {
        // Jump straight to next question, no feedback card
        setQuiz({ ...quiz, question: res.next_question!, concept: res.next_concept ?? "", difficulty: res.difficulty, questionsAsked: quiz.questionsAsked + 1 });
        setAnswer("");
        setFeedback(null);
        setPendingAnswer("");
        setPhase("question");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
      toast.error("Failed to skip question");
    } finally {
      setSubmitting(false);
    }
  }

  function handleNext() {
    if (!quiz || !feedback) return;
    setQuiz({ ...quiz, question: feedback.nextQuestion!, concept: feedback.nextConcept ?? "", difficulty: feedback.nextDifficulty, questionsAsked: quiz.questionsAsked + 1 });
    setAnswer("");
    setFeedback(null);
    setPendingAnswer("");
    setPhase("question");
  }

  function handleReset() {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    setTimedOut(false);
    setPhase("pick");
    setQuiz(null);
    setFeedback(null);
    setReport(null);
    setAnswer("");
    setError(null);
    setHistory([]);
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-2xl w-full mx-auto space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Quiz</h1>
        <p className="text-muted-foreground text-sm">
          Test your understanding with adaptive questions based on your documents.
        </p>
      </div>

      {/* ── Pick phase ── */}
      {phase === "pick" && (
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-4">
              <CardTitle className="text-base">Start a new quiz</CardTitle>
              <CardDescription>Choose a document and how many questions you want</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {docsLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-10 w-full" />
                </div>
              ) : docs.length === 0 ? (
                <div className="flex flex-col items-center gap-3 py-6 text-center">
                  <BookOpen className="h-8 w-8 text-muted-foreground/50" />
                  <div>
                    <p className="text-sm font-medium text-muted-foreground">No documents ready</p>
                    <p className="text-xs text-muted-foreground/70 mt-1">Upload a document first to start quizzing</p>
                  </div>
                  <Button asChild variant="outline" size="sm">
                    <Link href="/upload"><Upload className="mr-1.5 h-3.5 w-3.5" /> Upload document</Link>
                  </Button>
                </div>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <Label>Document</Label>
                    <Select value={selectedDocId} onValueChange={setSelectedDocId}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select a document…" />
                      </SelectTrigger>
                      <SelectContent>
                        {docs.map((d) => (
                          <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <Label>Number of questions</Label>
                      <span className="text-sm font-semibold tabular-nums">{maxQuestions}</span>
                    </div>
                    <input
                      type="range"
                      min={3}
                      max={10}
                      value={maxQuestions}
                      onChange={(e) => setMaxQuestions(Number(e.target.value))}
                      className="w-full accent-primary"
                    />
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>3</span><span>10</span>
                    </div>
                  </div>

                  <Button onClick={handleStart} disabled={!selectedDocId} className="w-full">
                    Start Quiz
                  </Button>
                </>
              )}
            </CardContent>
          </Card>

          {/* Past sessions */}
          {pastSessions.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Past sessions</h2>
              {pastSessions.map((s) => {
                const isOpen = expandedSession === s.session_id;
                const rep = sessionReports[s.session_id];
                const attempts = sessionAttempts[s.session_id];
                const isLoading = isOpen && (!rep || !attempts);
                return (
                  <Card key={s.session_id} className="overflow-hidden">
                    <button
                      className="w-full flex items-center justify-between px-5 py-4 hover:bg-muted/40 transition-colors text-left"
                      onClick={() => handleExpandSession(s.session_id)}
                    >
                      <div>
                        <p className="text-sm font-medium">{s.doc_name}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {new Date(s.created_at).toLocaleDateString()} · {s.questions_asked} questions ·{" "}
                          <ScoreBadge score={s.score} />
                        </p>
                      </div>
                      {isOpen ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
                    </button>

                    {isOpen && (
                      <div className="border-t px-5 py-4 space-y-4">
                        {isLoading && (
                          <div className="space-y-2">
                            <Skeleton className="h-3 w-full" />
                            <Skeleton className="h-3 w-4/5" />
                          </div>
                        )}

                        {rep && rep.concepts.length > 0 && (
                          <div className="space-y-2">
                            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">By concept</p>
                            <div className="divide-y rounded-lg border overflow-hidden">
                              {rep.concepts.map((c) => (
                                <div key={c.concept} className="flex items-center justify-between px-3 py-2 text-xs">
                                  <span className="font-medium">{c.concept}</span>
                                  <div className="flex items-center gap-3 text-muted-foreground">
                                    <span>{c.correct}/{c.total}</span>
                                    <ScoreBadge score={c.avg_confidence} className="text-xs" />
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {attempts && attempts.length > 0 && (
                          <div className="space-y-1.5">
                            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Questions</p>
                            {attempts.map((a, i) => (
                              <div key={a.id} className="rounded-lg border overflow-hidden">
                                <button
                                  className="w-full flex items-start gap-2 px-3 py-2.5 text-left hover:bg-muted/40 transition-colors"
                                  onClick={() => setExpandedAttempt(expandedAttempt === a.id ? null : a.id)}
                                >
                                  {a.correct
                                    ? <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0 mt-0.5" />
                                    : <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0 mt-0.5" />
                                  }
                                  <span className="flex-1 text-xs">{i + 1}. {a.question}</span>
                                  <span className="text-xs text-muted-foreground">{Math.round(a.confidence_score * 100)}%</span>
                                </button>
                                {expandedAttempt === a.id && (
                                  <div className="border-t bg-muted/20 px-3 py-2.5 space-y-2 text-xs">
                                    <div>
                                      <p className="text-muted-foreground mb-0.5">Your answer</p>
                                      <p className="italic">{a.user_answer}</p>
                                    </div>
                                    {a.ai_feedback && (
                                      <div>
                                        <p className="text-muted-foreground mb-0.5">Feedback</p>
                                        <p className="leading-relaxed">{a.ai_feedback}</p>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Loading ── */}
      {phase === "loading" && (
        <Card>
          <CardContent className="flex flex-col items-center gap-4 py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            <p className="text-sm text-muted-foreground">Generating your first question…</p>
          </CardContent>
        </Card>
      )}

      {/* ── Error ── */}
      {phase === "error" && (
        <Card className="border-destructive/50">
          <CardContent className="flex flex-col items-center gap-4 py-10 text-center">
            <XCircle className="h-8 w-8 text-destructive" />
            <div>
              <p className="font-medium text-sm">Something went wrong</p>
              <p className="text-xs text-muted-foreground mt-1">{error}</p>
            </div>
            <Button variant="outline" size="sm" onClick={handleReset}>
              <RotateCcw className="mr-2 h-3.5 w-3.5" /> Try again
            </Button>
          </CardContent>
        </Card>
      )}

      {/* ── Question / Evaluating ── */}
      {phase === "question" && quiz && (
        <div className="space-y-4">
          {/* Progress */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Question {quiz.questionsAsked + 1} of {quiz.maxQuestions}</span>
              <div className="flex items-center gap-2">
                {quiz.concept && <span className="font-medium text-foreground">{quiz.concept}</span>}
                {quiz.difficulty && (
                  <Badge variant="outline" className={cn("text-xs px-2 py-0", DIFFICULTY_BADGE[quiz.difficulty])}>
                    {quiz.difficulty}
                  </Badge>
                )}
              </div>
            </div>
            <Progress value={((quiz.questionsAsked) / quiz.maxQuestions) * 100} className="h-1.5" />
          </div>

          {/* Question card */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-medium leading-relaxed">{quiz.question}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Textarea
                rows={4}
                placeholder="Type your answer… (Ctrl+Enter to submit)"
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && e.ctrlKey && !submitting) handleSubmit(); }}
                disabled={submitting}
                className="resize-none"
              />
              <Button onClick={handleSubmit} disabled={!answer.trim() || submitting} className="w-full">
                {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {submitting ? "Evaluating…" : "Submit Answer"}
              </Button>
              <div className="flex justify-center">
                <button
                  onClick={handleSkip}
                  disabled={submitting && !timedOut}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                >
                  Skip this question
                </button>
              </div>
            </CardContent>
          </Card>

          {/* Taking too long banner */}
          {submitting && timedOut && (
            <Card className="border-amber-500/40 bg-amber-500/5">
              <CardContent className="py-4 flex items-center justify-between gap-4">
                <div className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-400">
                  <Loader2 className="h-4 w-4 animate-spin shrink-0" />
                  <span>Taking too long…</span>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={handleWait} className="h-7 px-3 text-xs">
                    Wait
                  </Button>
                  <Button size="sm" onClick={handleSkip} className="h-7 px-3 text-xs bg-amber-600 hover:bg-amber-700 text-white border-0">
                    Skip
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* ── Feedback ── */}
      {phase === "feedback" && quiz && feedback && (
        <div className="space-y-4">
          <div className="space-y-2">
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>Question {quiz.questionsAsked + 1} of {quiz.maxQuestions}</span>
            </div>
            <Progress value={((quiz.questionsAsked + 1) / quiz.maxQuestions) * 100} className="h-1.5" />
          </div>

          {/* Your answer */}
          <Card className="bg-muted/30">
            <CardContent className="py-4 space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Your answer</p>
              <p className="text-sm italic">{pendingAnswer}</p>
            </CardContent>
          </Card>

          {/* Feedback */}
          <Card className={cn("border-2", feedback.isCorrect ? "border-green-500/40 bg-green-500/5" : "border-red-500/40 bg-red-500/5")}>
            <CardContent className="py-5 space-y-3">
              <div className="flex items-center gap-2">
                {feedback.isCorrect
                  ? <CheckCircle2 className="h-5 w-5 text-green-500 shrink-0" />
                  : <XCircle className="h-5 w-5 text-red-500 shrink-0" />
                }
                <span className="font-semibold text-sm">
                  {feedback.isCorrect ? "Correct!" : "Not quite"}
                </span>
                <Badge variant="outline" className="ml-auto text-xs px-2 py-0">
                  {Math.round(feedback.confidence * 100)}% confidence
                </Badge>
              </div>
              <p className="text-sm leading-relaxed">{feedback.feedback}</p>
              {feedback.correctAnswer && (
                <>
                  <Separator />
                  <div>
                    <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1.5">Correct answer</p>
                    <p className="text-sm leading-relaxed text-blue-600 dark:text-blue-400">{feedback.correctAnswer}</p>
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <Button onClick={handleNext} className="w-full">
            Next Question <ArrowRight className="ml-2 h-4 w-4" />
          </Button>
        </div>
      )}

      {/* ── Done ── */}
      {phase === "done" && feedback && (
        <div className="space-y-5">
          {/* Hero */}
          <Card className="text-center">
            <CardContent className="py-8 space-y-3">
              <div className="flex justify-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-amber-500/10">
                  <Trophy className="h-8 w-8 text-amber-500" />
                </div>
              </div>
              <div>
                <h2 className="text-xl font-bold">Quiz complete!</h2>
                <p className="text-sm text-muted-foreground mt-1">
                  You answered {history.filter((h) => h.isCorrect).length} of {history.length} questions correctly.
                </p>
              </div>
              <Progress
                value={(history.filter((h) => h.isCorrect).length / history.length) * 100}
                className="h-2 max-w-xs mx-auto"
              />
            </CardContent>
          </Card>

          {/* Last feedback */}
          <Card className={cn("border-2", feedback.isCorrect ? "border-green-500/40 bg-green-500/5" : "border-red-500/40 bg-red-500/5")}>
            <CardContent className="py-4 space-y-2">
              <div className="flex items-center gap-2">
                {feedback.isCorrect ? <CheckCircle2 className="h-4 w-4 text-green-500" /> : <XCircle className="h-4 w-4 text-red-500" />}
                <span className="text-sm font-medium">Last question: {feedback.isCorrect ? "Correct" : "Incorrect"}</span>
              </div>
              <p className="text-sm leading-relaxed">{feedback.feedback}</p>
            </CardContent>
          </Card>

          {/* Concept report */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Performance by concept</CardTitle>
            </CardHeader>
            <CardContent>
              {reportLoading && (
                <div className="space-y-2">
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="h-4 w-4/5" />
                </div>
              )}
              {!reportLoading && report && report.concepts.length > 0 && (
                <div className="divide-y rounded-lg border overflow-hidden">
                  {report.concepts.map((c) => (
                    <div key={c.concept} className="px-3 py-2.5 space-y-1.5">
                      <div className="flex items-center justify-between text-sm">
                        <span className="font-medium">{c.concept}</span>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span>{c.correct}/{c.total}</span>
                          <ScoreBadge score={c.accuracy} className="text-xs" />
                        </div>
                      </div>
                      <Progress value={c.accuracy * 100} className="h-1" />
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Session recap */}
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Session recap</h3>
            {history.map((h, i) => (
              <Card key={i} className={cn("border", h.isCorrect ? "border-green-500/30" : "border-red-500/30")}>
                <CardContent className="py-3 space-y-1.5">
                  <div className="flex items-start gap-2">
                    {h.isCorrect ? <CheckCircle2 className="h-3.5 w-3.5 text-green-500 shrink-0 mt-0.5" /> : <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0 mt-0.5" />}
                    <p className="text-sm font-medium">{h.question}</p>
                  </div>
                  <p className="text-xs text-muted-foreground italic pl-5">Your answer: {h.answer}</p>
                  {!h.isCorrect && h.correctAnswer && (
                    <p className="text-xs text-blue-600 dark:text-blue-400 pl-5">Correct: {h.correctAnswer}</p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="flex gap-3">
            <Button variant="outline" onClick={handleReset} className="flex-1">
              <RotateCcw className="mr-2 h-4 w-4" /> New quiz
            </Button>
            <Button asChild className="flex-1">
              <Link href="/progress">View progress <ArrowRight className="ml-2 h-4 w-4" /></Link>
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
