"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Document, listDocuments, streamChat } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Send, FileText, MessageSquare, Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

interface Message {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

export default function ChatPage() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listDocuments()
      .then((all) => setDocs(all.filter((d) => d.status === "ready")))
      .catch((e) => toast.error(e.message))
      .finally(() => setDocsLoading(false));
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    if (!input.trim() || !selectedDoc || loading) return;
    const question = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setLoading(true);
    setMessages((prev) => [...prev, { role: "assistant", content: "", streaming: true }]);

    try {
      let accumulated = "";
      for await (const token of streamChat(question, selectedDoc.id)) {
        accumulated += token;
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { role: "assistant", content: accumulated, streaming: true };
          return next;
        });
      }
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: "assistant", content: accumulated, streaming: false };
        return next;
      });
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          content: `Sorry, something went wrong: ${err instanceof Error ? err.message : "Unknown error"}`,
          streaming: false,
        };
        return next;
      });
      toast.error("Chat request failed");
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex h-[calc(100vh-3rem)] -m-6 overflow-hidden">
      {/* Document sidebar */}
      <aside className="w-64 shrink-0 border-r bg-muted/30 flex flex-col">
        <div className="px-4 py-3 border-b">
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Documents
          </p>
        </div>

        <ScrollArea className="flex-1">
          <div className="p-2 space-y-0.5">
            {docsLoading &&
              Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="px-3 py-3 space-y-1.5">
                  <Skeleton className="h-3 w-4/5" />
                  <Skeleton className="h-2.5 w-2/5" />
                </div>
              ))}

            {!docsLoading && docs.length === 0 && (
              <div className="flex flex-col items-center justify-center gap-3 py-8 px-4 text-center">
                <FileText className="h-8 w-8 text-muted-foreground/50" />
                <div>
                  <p className="text-xs font-medium text-muted-foreground">No documents ready</p>
                  <p className="text-xs text-muted-foreground/70 mt-1">
                    Upload a document first
                  </p>
                </div>
                <Button asChild variant="outline" size="sm" className="text-xs">
                  <Link href="/upload">
                    <Upload className="mr-1.5 h-3 w-3" /> Upload
                  </Link>
                </Button>
              </div>
            )}

            {docs.map((doc) => (
              <button
                key={doc.id}
                onClick={() => {
                  setSelectedDoc(doc);
                  setMessages([]);
                }}
                className={cn(
                  "w-full text-left px-3 py-3 rounded-lg transition-colors",
                  selectedDoc?.id === doc.id
                    ? "bg-background shadow-sm border border-border"
                    : "hover:bg-background/50 text-muted-foreground"
                )}
              >
                <div className="flex items-start gap-2">
                  <FileText className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  <div className="min-w-0">
                    <p className="text-xs font-medium truncate text-foreground">{doc.name}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {new Date(doc.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </ScrollArea>
      </aside>

      {/* Chat area */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center gap-3 border-b px-6 py-3">
          {selectedDoc ? (
            <>
              <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
              <p className="text-sm font-medium truncate">{selectedDoc.name}</p>
              <Badge variant="secondary" className="text-xs ml-auto shrink-0">Ready</Badge>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Select a document to start chatting</p>
          )}
        </div>

        {/* Messages */}
        <ScrollArea className="flex-1 px-6 py-6">
          {!selectedDoc && (
            <div className="flex flex-col items-center justify-center h-full gap-4 py-20">
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-muted">
                <MessageSquare className="h-7 w-7 text-muted-foreground" />
              </div>
              <div className="text-center">
                <p className="font-medium text-sm">Chat with your document</p>
                <p className="text-xs text-muted-foreground mt-1 max-w-xs">
                  Select a document from the sidebar to start asking questions about it.
                </p>
              </div>
            </div>
          )}

          {selectedDoc && messages.length === 0 && !loading && (
            <div className="flex flex-col items-center justify-center gap-3 py-20 text-center">
              <p className="text-sm text-muted-foreground">
                Ask anything about{" "}
                <span className="font-medium text-foreground">{selectedDoc.name}</span>
              </p>
              <div className="flex flex-wrap gap-2 justify-center max-w-sm">
                {["Summarise this document", "What are the key concepts?", "Explain the main argument"].map((q) => (
                  <button
                    key={q}
                    onClick={() => { setInput(q); }}
                    className="text-xs px-3 py-1.5 rounded-full border border-border hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-6">
            {messages.map((msg, i) => (
              <div
                key={i}
                className={cn("flex gap-3", msg.role === "user" ? "flex-row-reverse" : "flex-row")}
              >
                <Avatar className="h-7 w-7 shrink-0">
                  <AvatarFallback className={cn(
                    "text-xs font-semibold",
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-muted-foreground"
                  )}>
                    {msg.role === "user" ? "U" : "T"}
                  </AvatarFallback>
                </Avatar>
                <div
                  className={cn(
                    "max-w-[72%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap",
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground rounded-tr-sm"
                      : "bg-muted rounded-tl-sm"
                  )}
                >
                  {msg.content}
                  {msg.streaming && (
                    <span className="inline-block w-1.5 h-3.5 ml-1 bg-current opacity-60 animate-pulse rounded-sm align-middle" />
                  )}
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>

        {/* Input */}
        <div className="border-t px-6 py-4">
          <div className="flex gap-3 items-end">
            <Textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!selectedDoc || loading}
              placeholder={
                selectedDoc
                  ? "Ask a question… (Enter to send, Shift+Enter for newline)"
                  : "Select a document first"
              }
              className="resize-none min-h-[42px] max-h-40"
            />
            <Button
              onClick={handleSend}
              disabled={!selectedDoc || !input.trim() || loading}
              size="icon"
              className="shrink-0 h-[42px] w-[42px]"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
