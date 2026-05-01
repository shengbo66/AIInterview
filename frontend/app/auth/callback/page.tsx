"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { exchangeCodeForTokens } from "@/lib/auth";

function CallbackInner() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = params.get("code");
    if (!code) {
      setError("missing code");
      return;
    }
    exchangeCodeForTokens(code)
      .then(() => router.replace("/"))
      .catch((e) => setError(e.message));
  }, [params, router]);

  if (error) {
    return (
      <div className="p-8 text-red-400">
        登录失败: {error}
        <br />
        <a href="/" className="text-sky-400 underline mt-2 inline-block">返回首页</a>
      </div>
    );
  }
  return <div className="p-8 text-neutral-400">登录中...</div>;
}

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<div className="p-8 text-neutral-400">加载中...</div>}>
      <CallbackInner />
    </Suspense>
  );
}
