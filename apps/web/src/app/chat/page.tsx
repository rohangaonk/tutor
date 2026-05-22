"use client";

import { useEffect, useRef, useState } from "react";
import { Document, listDocuments, streamChat } from "@/lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
}

export default function ChatPage() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [docsError, setDocsError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listDocuments()
      .then((all) => setDocs(all.filter((d) => d.status === "ready")))
      .catch((e) => setDocsError(e.message));
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

    // Append placeholder for the streaming reply
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", streaming: true },
    ]);

    try {
      let accumulated = "";
      for await (const token of streamChat(question, selectedDoc.id)) {
        accumulated += token;
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            role: "assistant",
            content: accumulated,
            streaming: true,
          };
          return next;
        });
      }
      // Mark streaming done
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          content: accumulated,
          streaming: false,
        };
        return next;
      });
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: "assistant",
          content: `Error: ${err instanceof Error ? err.message : "Something went wrong."}`,
          streaming: false,
        };
        return next;
      });
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

  // ── Sidebar ───────────────────────────────────────────────────────────────

  const sidebar = (
    <aside className="w-64 shrink-0 border-r border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 flex flex-col">
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-800">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
          Ready documents
        </h2>
      </div>

      <div className="flex-1 overflow-y-auto py-2">
        {docsError && (
          <p className="px-4 py-3 text-xs text-red-500">{docsError}</p>
        )}
        {docs.length === 0 && !docsError && (
          <p className="px-4 py-3 text-xs text-zinc-400">
            No ready documents.{" "}
            <a href="/upload" className="text-blue-500 hover:underline">
              Upload one →
            </a>
          </p>
        )}
        {docs.map((doc) => (
          <button
            key={doc.id}
            onClick={() => {
              setSelectedDoc(doc);
              setMessages([]);
            }}
            className={`
              w-full text-left px-4 py-3 text-sm transition-colors
              ${
                selectedDoc?.id === doc.id
                  ? "bg-zinc-100 dark:bg-zinc-800 font-medium"
                  : "hover:bg-zinc-50 dark:hover:bg-zinc-800/50 text-zinc-600 dark:text-zinc-400"
              }
            `}
          >
            <span className="block truncate">{doc.name}</span>
            <span className="block text-xs text-zinc-400 mt-0.5">
              {new Date(doc.created_at).toLocaleDateString()}
            </span>
          </button>
        ))}
      </div>
    </aside>
  );

  // ── Chat area ─────────────────────────────────────────────────────────────

  const chatArea = (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 flex flex-col gap-6">
        {!selectedDoc && (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-zinc-400 text-sm">
              Select a document from the sidebar to start chatting.
            </p>
          </div>
        )}

        {selectedDoc && messages.length === 0 && (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-zinc-400 text-sm">
              Ask anything about{" "}
              <span className="font-medium text-zinc-600 dark:text-zinc-300">
                {selectedDoc.name}
              </span>
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            {msg.role === "assistant" && (
              <div className="size-7 rounded-full bg-zinc-200 dark:bg-zinc-700 shrink-0 flex items-center justify-center text-xs font-bold text-zinc-600 dark:text-zinc-300">
                T
              </div>
            )}
            <div
              className={`
                max-w-[70%] rounded-2xl px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap
                ${
                  msg.role === "user"
                    ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900 rounded-br-sm"
                    : "bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-bl-sm"
                }
              `}
            >
              {msg.content}
              {msg.streaming && (
                <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-current opacity-70 animate-pulse rounded-sm" />
              )}
            </div>
            {msg.role === "user" && (
              <div className="size-7 rounded-full bg-blue-600 shrink-0 flex items-center justify-center text-xs font-bold text-white">
                U
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-6 py-4">
        <div className="flex gap-3 items-end">
          <textarea
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
            className="
              flex-1 resize-none rounded-xl border border-zinc-300 dark:border-zinc-700
              bg-transparent px-4 py-2.5 text-sm focus:outline-none
              focus:ring-2 focus:ring-zinc-400 dark:focus:ring-zinc-600
              disabled:opacity-40 placeholder:text-zinc-400
            "
          />
          <button
            onClick={handleSend}
            disabled={!selectedDoc || !input.trim() || loading}
            className="
              shrink-0 px-4 py-2.5 rounded-xl text-sm font-medium
              bg-zinc-900 text-white dark:bg-white dark:text-zinc-900
              hover:opacity-90 transition-opacity
              disabled:opacity-40 disabled:cursor-not-allowed
            "
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex-1 flex min-h-0 h-full">
      {sidebar}
      {chatArea}
    </div>
  );
}
