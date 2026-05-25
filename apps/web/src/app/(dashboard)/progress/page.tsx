"use client";

import { useEffect, useState } from "react";
import { getProgress, DocumentProgress, ProgressResponse } from "@/lib/api";

function StrengthBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const colour =
    pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full ${colour} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 w-8 text-right">{pct}%</span>
    </div>
  );
}

function DocCard({ doc }: { doc: DocumentProgress }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-5 py-4 hover:bg-gray-750 transition-colors text-left"
        onClick={() => setOpen((o) => !o)}
      >
        <div>
          <p className="font-medium text-gray-100">{doc.doc_name}</p>
          <p className="text-xs text-gray-400 mt-0.5">
            {doc.sessions_completed} session{doc.sessions_completed !== 1 ? "s" : ""} completed
            {doc.sessions_completed > 0 &&
              ` · avg score ${Math.round(doc.avg_session_score * 100)}%`}
          </p>
        </div>
        <span className="text-gray-500 text-sm">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-5 pb-5 space-y-3 border-t border-gray-700 pt-4">
          {doc.topics.length === 0 ? (
            <p className="text-sm text-gray-500">No topics recorded yet.</p>
          ) : (
            doc.topics.map((t) => (
              <div key={t.topic}>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-gray-300">{t.topic}</span>
                  <span className="text-xs text-gray-500">
                    {new Date(t.updated_at).toLocaleDateString()}
                  </span>
                </div>
                <StrengthBar score={t.strength_score} />
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default function ProgressPage() {
  const [data, setData] = useState<ProgressResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getProgress()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100 flex flex-col items-center py-12 px-4">
      <h1 className="text-3xl font-bold mb-2">Progress</h1>

      {loading && (
        <p className="text-gray-400 animate-pulse mt-8">Loading progress…</p>
      )}

      {error && (
        <p className="text-red-400 mt-8">{error}</p>
      )}

      {data && !loading && (
        <div className="w-full max-w-2xl space-y-6 mt-8">
          {/* Overall strength */}
          <div className="bg-gray-800 rounded-xl border border-gray-700 px-5 py-4 flex items-center justify-between">
            <span className="text-gray-300 font-medium">Overall strength</span>
            <div className="flex items-center gap-3 w-48">
              <StrengthBar score={data.overall_strength} />
            </div>
          </div>

          {data.documents.length === 0 ? (
            <p className="text-gray-500 text-sm text-center">
              Complete a quiz to see progress here.
            </p>
          ) : (
            data.documents.map((doc) => (
              <DocCard key={doc.doc_id} doc={doc} />
            ))
          )}

          <button
            onClick={() => {
              setLoading(true);
              setError(null);
              getProgress()
                .then(setData)
                .catch((e) => setError(e.message))
                .finally(() => setLoading(false));
            }}
            className="w-full py-2 text-sm text-gray-500 hover:text-gray-300 transition-colors"
          >
            Refresh
          </button>
        </div>
      )}
    </div>
  );
}
