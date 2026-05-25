"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken, getStoredEmail, getToken } from "@/lib/api";

export default function NavBar() {
  const router = useRouter();
  const pathname = usePathname();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (getToken()) {
      setEmail(getStoredEmail());
    }
  }, [pathname]); // re-check on navigation (e.g. after sign in)

  if (pathname === "/login") return null;

  function handleSignOut() {
    clearToken();
    router.push("/login");
  }

  const linkClass =
    "text-sm text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors";

  return (
    <header className="border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900">
      <nav className="max-w-5xl mx-auto px-6 h-14 flex items-center gap-8">
        <Link href="/" className="font-semibold text-lg tracking-tight">
          Tutor
        </Link>
        <Link href="/upload" className={linkClass}>Upload</Link>
        <Link href="/chat" className={linkClass}>Chat</Link>
        <Link href="/quiz" className={linkClass}>Quiz</Link>
        <Link href="/progress" className={linkClass}>Progress</Link>

        <div className="ml-auto flex items-center gap-4">
          {email && (
            <span className="text-sm text-zinc-400 dark:text-zinc-500 truncate max-w-[180px]">
              {email}
            </span>
          )}
          <button onClick={handleSignOut} className={linkClass}>
            Sign out
          </button>
        </div>
      </nav>
    </header>
  );
}
