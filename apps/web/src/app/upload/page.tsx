"use client";

import { useRef, useState } from "react";
import { confirmUpload, presignUpload, uploadToS3 } from "@/lib/api";

type Stage = "idle" | "uploading" | "done" | "error";

export default function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  function handleFileSelect(selected: File | null) {
    if (!selected) return;
    const ok =
      selected.name.endsWith(".pdf") || selected.name.endsWith(".docx");
    if (!ok) {
      setError("Only PDF and DOCX files are supported.");
      return;
    }
    setFile(selected);
    setError(null);
    setStage("idle");
    setDocumentId(null);
  }

  async function handleUpload() {
    if (!file) return;
    setStage("uploading");
    setError(null);
    try {
      const { presigned_url, s3_key } = await presignUpload(
        file.name,
        file.type
      );
      await uploadToS3(presigned_url, file);
      const { document_id } = await confirmUpload(file.name, s3_key);
      setDocumentId(document_id);
      setStage("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setStage("error");
    }
  }

  return (
    <div className="max-w-2xl mx-auto w-full px-6 py-16 flex flex-col gap-8">
      <div>
        <h1 className="text-2xl font-semibold">Upload a document</h1>
        <p className="mt-1 text-sm text-zinc-500">
          PDF or DOCX — the document will be chunked and embedded automatically.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFileSelect(e.dataTransfer.files[0] ?? null);
        }}
        className={`
          flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed
          px-6 py-14 cursor-pointer transition-colors
          ${dragging
            ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30"
            : "border-zinc-300 dark:border-zinc-700 hover:border-zinc-400 dark:hover:border-zinc-600"
          }
        `}
      >
        <svg className="size-10 text-zinc-400" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
        </svg>
        <p className="text-sm text-zinc-500">
          {file ? (
            <span className="font-medium text-zinc-800 dark:text-zinc-200">{file.name}</span>
          ) : (
            <>Drag & drop or <span className="text-blue-600 dark:text-blue-400 font-medium">browse</span></>
          )}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx"
          className="hidden"
          onChange={(e) => handleFileSelect(e.target.files?.[0] ?? null)}
        />
      </div>

      {/* Upload button */}
      <button
        onClick={handleUpload}
        disabled={!file || stage === "uploading" || stage === "done"}
        className="
          self-start px-5 py-2.5 rounded-lg text-sm font-medium
          bg-zinc-900 text-white dark:bg-white dark:text-zinc-900
          hover:opacity-90 transition-opacity
          disabled:opacity-40 disabled:cursor-not-allowed
        "
      >
        {stage === "uploading" ? "Uploading…" : "Upload"}
      </button>

      {/* Status messages */}
      {stage === "done" && documentId && (
        <div className="rounded-lg bg-green-50 dark:bg-green-950/40 border border-green-200 dark:border-green-800 p-4 flex flex-col gap-2">
          <p className="text-sm font-medium text-green-800 dark:text-green-300">
            Upload successful — ingestion started in the background.
          </p>
          <p className="text-xs text-green-700 dark:text-green-400 font-mono break-all">
            Document ID: {documentId}
          </p>
          <a
            href="/chat"
            className="text-xs text-blue-600 dark:text-blue-400 hover:underline mt-1"
          >
            Go to Chat →
          </a>
        </div>
      )}

      {error && (
        <p className="rounded-lg bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 p-4 text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
