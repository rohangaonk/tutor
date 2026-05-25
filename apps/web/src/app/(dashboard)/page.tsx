export default function Home() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center px-6 py-24 gap-10">
      <div className="text-center flex flex-col gap-3">
        <h1 className="text-4xl font-semibold tracking-tight">Tutor</h1>
        <p className="text-zinc-500 text-lg max-w-md">
          Upload a document, then chat with it or take a quiz to test your understanding.
        </p>
      </div>

      <div className="flex gap-4">
        <a
          href="/upload"
          className="px-6 py-3 rounded-xl bg-zinc-900 text-white dark:bg-white dark:text-zinc-900 text-sm font-medium hover:opacity-90 transition-opacity"
        >
          Upload document
        </a>
        <a
          href="/chat"
          className="px-6 py-3 rounded-xl border border-zinc-300 dark:border-zinc-700 text-sm font-medium hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          Chat
        </a>
        <a
          href="/quiz"
          className="px-6 py-3 rounded-xl border border-zinc-300 dark:border-zinc-700 text-sm font-medium hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          Quiz
        </a>
        <a
          href="/progress"
          className="px-6 py-3 rounded-xl border border-zinc-300 dark:border-zinc-700 text-sm font-medium hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          Progress
        </a>
      </div>
    </div>
  );
}


