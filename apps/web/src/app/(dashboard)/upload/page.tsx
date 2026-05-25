"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { confirmUpload, presignUpload, uploadToS3 } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Upload, FileText, CheckCircle2, Loader2, AlertCircle, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

type Stage = "idle" | "uploading" | "done" | "error";

export default function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  function handleFileSelect(selected: File | null) {
    if (!selected) return;
    const ok = selected.name.endsWith(".pdf") || selected.name.endsWith(".docx");
    if (!ok) {
      toast.error("Only PDF and DOCX files are supported.");
      return;
    }
    setFile(selected);
    setStage("idle");
    setDocumentId(null);
  }

  async function handleUpload() {
    if (!file) return;
    setStage("uploading");
    try {
      const { presigned_url, s3_key } = await presignUpload(file.name, file.type);
      await uploadToS3(presigned_url, file);
      const { document_id } = await confirmUpload(file.name, s3_key);
      setDocumentId(document_id);
      setStage("done");
      toast.success("Upload successful — processing has started.");
    } catch (err) {
      setStage("error");
      toast.error(err instanceof Error ? err.message : "Upload failed.");
    }
  }

  function reset() {
    setFile(null);
    setStage("idle");
    setDocumentId(null);
  }

  const uploading = stage === "uploading";
  const done = stage === "done";

  return (
    <div className="max-w-2xl w-full mx-auto space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Upload a document</h1>
        <p className="text-muted-foreground text-sm">
          PDF or DOCX — it will be chunked and embedded automatically so you can chat or quiz yourself.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-base">Select file</CardTitle>
          <CardDescription>Drag and drop or click to browse</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Drop zone */}
          <div
            role="button"
            tabIndex={0}
            onClick={() => !done && inputRef.current?.click()}
            onKeyDown={(e) => e.key === "Enter" && !done && inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              handleFileSelect(e.dataTransfer.files[0] ?? null);
            }}
            className={cn(
              "flex flex-col items-center justify-center gap-4 rounded-xl border-2 border-dashed",
              "px-6 py-14 cursor-pointer transition-all select-none",
              dragging
                ? "border-primary bg-primary/5 scale-[1.01]"
                : done
                  ? "border-green-500 bg-green-500/5 cursor-default"
                  : "border-border hover:border-primary/50 hover:bg-muted/40"
            )}
          >
            {done ? (
              <>
                <CheckCircle2 className="h-10 w-10 text-green-500" />
                <div className="text-center">
                  <p className="font-medium text-sm">{file?.name}</p>
                  <p className="text-xs text-muted-foreground mt-1">Upload complete</p>
                </div>
              </>
            ) : file ? (
              <>
                <FileText className="h-10 w-10 text-primary" />
                <div className="text-center">
                  <p className="font-medium text-sm">{file.name}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {(file.size / 1024 / 1024).toFixed(2)} MB
                    {" · "}
                    <Badge variant="secondary" className="text-xs px-1 py-0">
                      {file.name.split(".").pop()?.toUpperCase()}
                    </Badge>
                  </p>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); reset(); }}
                    className="text-xs text-muted-foreground hover:text-foreground mt-2 underline underline-offset-2"
                  >
                    Remove
                  </button>
                </div>
              </>
            ) : (
              <>
                <div className="flex h-14 w-14 items-center justify-center rounded-xl bg-muted">
                  <Upload className="h-6 w-6 text-muted-foreground" />
                </div>
                <div className="text-center">
                  <p className="text-sm font-medium">
                    Drop your file here, or{" "}
                    <span className="text-primary">browse</span>
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">PDF, DOCX — up to 50 MB</p>
                </div>
              </>
            )}
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.docx"
            className="hidden"
            onChange={(e) => handleFileSelect(e.target.files?.[0] ?? null)}
          />

          {/* Actions */}
          {!done ? (
            <Button
              onClick={handleUpload}
              disabled={!file || uploading}
              className="w-full"
            >
              {uploading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {uploading ? "Uploading…" : "Upload document"}
            </Button>
          ) : (
            <div className="space-y-3">
              <Alert className="border-green-500/30 bg-green-500/10 text-green-700 dark:text-green-400">
                <CheckCircle2 className="h-4 w-4 text-green-500" />
                <AlertDescription className="text-xs">
                  Processing started in the background. Your document will be ready in a moment.
                  {documentId && (
                    <span className="block mt-1 font-mono text-[10px] opacity-60 break-all">
                      ID: {documentId}
                    </span>
                  )}
                </AlertDescription>
              </Alert>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={reset} className="flex-1">
                  Upload another
                </Button>
                <Button asChild size="sm" className="flex-1">
                  <Link href="/chat">
                    Go to Chat <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
                  </Link>
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Info */}
      <Card className="bg-muted/40 border-dashed">
        <CardContent className="py-4">
          <div className="flex gap-3">
            <AlertCircle className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
            <div className="space-y-1 text-xs text-muted-foreground">
              <p>After uploading, the document is processed asynchronously. This typically takes 10–60 seconds depending on file size.</p>
              <p>Once ready, it will be available for Chat and Quiz sessions.</p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
