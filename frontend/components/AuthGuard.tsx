"use client";

import { useEffect, useState } from "react";
import { getAccessToken, redirectToLogin, isAuthEnabled } from "@/lib/auth";

/**
 * Wrap pages that require login. If no token in sessionStorage, redirect
 * to Cognito Hosted UI.
 *
 * If auth is disabled (no Cognito config in env), passes through.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    if (!isAuthEnabled()) {
      setAuthed(true);
      return;
    }
    const token = getAccessToken();
    if (!token) {
      redirectToLogin();
      return;
    }
    setAuthed(true);
  }, []);

  if (authed === null) {
    return <div className="p-8 text-neutral-400">检查登录中...</div>;
  }
  return <>{children}</>;
}
