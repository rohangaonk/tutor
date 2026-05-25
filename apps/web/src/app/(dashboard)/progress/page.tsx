"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getProgress, DocumentProgress, ProgressResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  TrendingUp,
  ChevronDown,
  ChevronUp,
  Trophy,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

function strengthColor(score: number) {
  if (score >= 0.7) return "text-green-600";
  if (score >= 0.4) return "text-amber-600";
  return "text-red-600";
}

function StrengthBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <div className="flex items-center gap-3">
      <Progress value={pct} className="flex-1 h-2" />
      <span className={cn("text-xs font-semibold tabular-nums w-8 text-right", strengthColor(score))}>
        {pct}%
      </span>
    </div>
  );
}

function DocCard({ doc }: { doc: DocumentProgress }) {
  const [open, setOpen] = useState(true);
  const avgPct = Math.round(doc.avg_session_score * 100);

  return (
    <Card className="overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-muted/40 transition-colors text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <div className="min-w-0">
          <p className="font-medium text-sm truncate">{doc.doc_name}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {doc.sessions_completed} session{doc.sessions_completed !== 1 ? "s" : ""} completed
            {doc.sessions_completed > 0 && (
              <>
                {" · avg score "}
                <span className={cn("font-semibold", strengthColor(doc.avg_session_score))}>
                  {avgPct}%
                </span>
              </>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-4">
          {doc.sessions_completed > 0 && (
            <Badge
              variant="outline"
              className={cn(
                "text-xs px-2 py-0",
                avgPct >= 70
                  ? "border-green-500/30 text-green-600 bg-green-500/5"
                  : avgPct >= 40
                  ? "border-amber-500/30 text-amber-600 bg-amber-500/5"
                  : "border-red-500/30 text-red-600 bg-red-500/5"
              )}
            >
              {avgPct >= 70 ? "Strong" : avgPct >= 40 ? "Improving" : "Needs work"}
            </Badge>
          )}
          {open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
        </div>
      </button>

      {open && (
        <>
          <Separator />
          <CardContent className="py-4 space-y-3">
            {doc.topics.length === 0 ? (
              <p className="text-sm text-muted-foreground">No topic data yet. Complete a quiz to see results.</p>
            ) : (
              doc.topics.map((t) => (
                <div key={t.topic} className="space-y-1.5">
                  <div className="flex justify-between text-sm">
                    <span className="font-medium">{t.topic}</span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(t.updated_at).toLocaleDateString()}
                    </span>
                  </div>
                  <StrengthBar score={t.strength_score} />
                </div>
              ))
            )}
          </CardContent>
        </>
      )}
    </Card>
  );
}

export default function ProgressPage() {
  const [data, setData] = useState<ProgressResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function fetchData(isRefresh = false) {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    getProgress()
      .then(setData)
      .catch((e) => {
        setError(e.message);
        toast.error("Failed to load progress");
      })
      .finally(() => {
        setLoading(false);
        setRefreshing(false);
      });
  }

  useEffect(() => { fetchData(); }, []);

  const overallPct = data ? Math.round(data.overall_strength * 100) : 0;

  return (
    <div className="max-w-2xl w-full mx-auto space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">Progress</h1>
          <p className="text-muted-foreground text-sm">
            Your topic strengths and quiz performance across all documents.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => fetchData(true)}
          disabled={refreshing || loading}
          className="shrink-0"
        >
          <RefreshCw className={cn("mr-2 h-3.5 w-3.5", refreshing && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {/* Loading */}
      {loading && (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-36 w-full rounded-xl" />
          <Skeleton className="h-36 w-full rounded-xl" />
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <Card className="border-destructive/50">
          <CardContent className="flex items-center gap-3 py-5">
            <AlertCircle className="h-5 w-5 text-destructive shrink-0" />
            <p className="text-sm text-muted-foreground">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Data */}
      {data && !loading && (
        <div className="space-y-5">
          {/* Overall strength */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm flex items-center gap-2">
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
                Overall strength
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex items-center gap-4">
                <div className="flex-1">
                  <Progress value={overallPct} className="h-3" />
                </div>
                <span className={cn("text-2xl font-bold tabular-nums", strengthColor(data.overall_strength))}>
                  {overallPct}%
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                Based on {data.documents.reduce((s, d) => s + d.sessions_completed, 0)} completed quiz session{data.documents.reduce((s, d) => s + d.sessions_completed, 0) !== 1 ? "s" : ""} across {data.documents.length} document{data.documents.length !== 1 ? "s" : ""}
              </p>
            </CardContent>
          </Card>

          {data.documents.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted">
                  <Trophy className="h-6 w-6 text-muted-foreground" />
                </div>
                <div>
                  <p className="font-medium text-sm">No progress yet</p>
                  <p className="text-xs text-muted-foreground mt-1 max-w-xs">
                    Complete a quiz session to start tracking your learning progress.
                  </p>
                </div>
                <Button asChild variant="outline" size="sm">
                  <Link href="/quiz">Take a quiz</Link>
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {data.documents.map((doc) => (
                <DocCard key={doc.doc_id} doc={doc} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
