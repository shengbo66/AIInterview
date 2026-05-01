"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthGuard } from "./AuthGuard";
import { getUserEmail, isAuthEnabled, logout } from "@/lib/auth";

/**
 * Wraps the app with nav bar + AuthGuard.
 * /auth/callback is exempt from AuthGuard (it IS the auth flow).
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    setEmail(getUserEmail());
  }, [pathname]);

  const isCallback = pathname?.startsWith("/auth/");
  const content = isCallback ? children : <AuthGuard>{children}</AuthGuard>;

  return (
    <>
      <nav className="border-b border-neutral-800 px-6 py-3 flex items-center gap-6 text-sm">
        <Link href="/" className="font-semibold text-sky-400 hover:text-sky-300">
          🎤 AI 面试
        </Link>
        <Link href="/history" className="text-neutral-400 hover:text-neutral-200">
          历史记录
        </Link>
        <div className="ml-auto flex items-center gap-3 text-xs text-neutral-500">
          {email && <span>{email}</span>}
          {isAuthEnabled() && email && (
            <button
              onClick={logout}
              className="text-neutral-400 hover:text-neutral-200 underline"
            >
              登出
            </button>
          )}
        </div>
      </nav>
      <main className="flex-1">{content}</main>
    </>
  );
}
