"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { getToken } from "@/lib/api";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (pathname === "/login") {
      // Already signed in → go to dashboard
      if (getToken()) {
        router.replace("/");
      } else {
        setChecked(true);
      }
      return;
    }
    if (!getToken()) {
      router.replace("/login");
    } else {
      setChecked(true);
    }
  }, [router, pathname]);

  if (!checked) return null;
  return <>{children}</>;
}
