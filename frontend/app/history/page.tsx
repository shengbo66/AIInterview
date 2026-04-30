"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchInterviews, type InterviewSummary } from "@/lib/api";

function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });
}

function durationMin(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms <= 0) return "< 1 分钟";
  return `${Math.round(ms / 60000)} 分钟`;
}

const STATUS_LABEL: Record<string, string> = {
  in_progress: "进行中",
  completed: "已完成",
  abandoned: "未完成",
  evaluation_pending: "评估中",
  evaluation_completed: "已评估",
  evaluation_failed: "评估失败",
};

export default function HistoryPage() {
  const [interviews, setInterviews] = useState<InterviewSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchInterviews()
      .then((data) => {
        // Sort by created_at desc
        data.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
        setInterviews(data);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-neutral-400">加载中...</div>;
  if (error) return <div className="p-8 text-red-400">加载失败: {error}</div>;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-4">
      <h1 className="text-xl font-semibold">面试历史</h1>

      {interviews.length === 0 ? (
        <div className="text-neutral-500 py-12 text-center">
          <p>还没有面试记录</p>
          <Link href="/" className="text-sky-400 hover:text-sky-300 mt-2 inline-block">
            开始面试 →
          </Link>
        </div>
      ) : (
        <div className="space-y-2">
          {interviews.map((iv) => (
            <Link
              key={iv.id}
              href={`/history/${iv.id}`}
              className="block border border-neutral-800 rounded-lg p-4 hover:border-neutral-600 transition-colors"
            >
              <div className="flex justify-between items-start">
                <div>
                  <span className="text-sm font-medium">
                    {iv.company_name} · {iv.role_title}
                  </span>
                  <p className="text-xs text-neutral-500 mt-1">{fmtDate(iv.created_at)}</p>
                </div>
                <div className="text-right">
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    iv.status === "completed" || iv.status === "evaluation_completed"
                      ? "bg-emerald-900 text-emerald-300"
                      : iv.status === "in_progress"
                        ? "bg-sky-900 text-sky-300"
                        : "bg-neutral-800 text-neutral-400"
                  }`}>
                    {STATUS_LABEL[iv.status] ?? iv.status}
                  </span>
                  <p className="text-xs text-neutral-500 mt-1">
                    {durationMin(iv.bidi_started_at, iv.bidi_ended_at)}
                  </p>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
