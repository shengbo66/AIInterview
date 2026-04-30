"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { fetchInterview, fetchAudioUrl, type InterviewDetail, type EvaluationOut } from "@/lib/api";

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString("zh-CN", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

function durationMin(start: string | null, end: string | null): string {
  if (!start || !end) return "—";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms <= 0) return "< 1 分钟";
  return `${Math.round(ms / 60000)} 分钟`;
}

function ScoreBadge({ score, label }: { score: number | null; label: string }) {
  if (score == null) return null;
  const color =
    score >= 80 ? "text-emerald-400" : score >= 60 ? "text-yellow-400" : "text-red-400";
  return (
    <div className="text-center">
      <div className={`text-2xl font-bold ${color}`}>{score}</div>
      <div className="text-xs text-neutral-500">{label}</div>
    </div>
  );
}

function PlayButton({
  interviewId,
  questionId,
  role,
}: {
  interviewId: string;
  questionId: string;
  role: "assistant" | "user";
}) {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const play = async () => {
    try {
      const url = await fetchAudioUrl(interviewId, questionId, role);
      if (audioRef.current) {
        audioRef.current.pause();
      }
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => setPlaying(false);
      audio.onerror = () => setPlaying(false);
      setPlaying(true);
      await audio.play();
    } catch {
      setPlaying(false);
    }
  };

  const stop = () => {
    audioRef.current?.pause();
    setPlaying(false);
  };

  return (
    <button
      onClick={playing ? stop : play}
      className="text-xs text-neutral-500 hover:text-neutral-300 ml-1"
      title={playing ? "停止" : "播放音频"}
    >
      {playing ? "⏹" : "▶️"}
    </button>
  );
}

export default function InterviewDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [data, setData] = useState<InterviewDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    fetchInterview(id)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="p-8 text-neutral-400">加载中...</div>;
  if (error) return <div className="p-8 text-red-400">加载失败: {error}</div>;
  if (!data) return <div className="p-8 text-red-400">未找到面试记录</div>;

  // Build evaluation lookup: question_id → EvaluationOut
  const evalMap = new Map<string, EvaluationOut>();
  const overallEval = data.evaluations.find((e) => !e.question_id);
  for (const ev of data.evaluations) {
    if (ev.question_id) evalMap.set(ev.question_id, ev);
  }

  const sortedQuestions = [...data.questions].sort((a, b) => a.order_index - b.order_index);

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <Link href="/history" className="text-sm text-neutral-500 hover:text-neutral-300">
          ← 返回列表
        </Link>
        <h1 className="text-xl font-semibold mt-2">
          {data.company_name} · {data.role_title}
        </h1>
        <div className="flex gap-4 text-xs text-neutral-500 mt-1">
          <span>{fmtDate(data.created_at)}</span>
          <span>{durationMin(data.bidi_started_at, data.bidi_ended_at)}</span>
          <span>{sortedQuestions.length} 题</span>
          <span>{data.bidi_tokens_total} tokens · ${data.bidi_cost_usd.toFixed(4)}</span>
        </div>
      </div>

      {/* Overall evaluation */}
      {overallEval && (
        <div className="border border-neutral-800 rounded-lg p-4 space-y-3">
          <h2 className="text-sm font-semibold text-neutral-300">整体评估</h2>
          <div className="flex gap-8 justify-center">
            <ScoreBadge score={overallEval.overall_score} label="总分" />
            <ScoreBadge score={overallEval.content_score} label="内容" />
            <ScoreBadge score={overallEval.expression_score} label="表达" />
            <ScoreBadge score={overallEval.voice_score} label="语音" />
          </div>
          {overallEval.overall_result && (
            <p className="text-sm text-neutral-300">{overallEval.overall_result}</p>
          )}
          {overallEval.improvement_suggestion && (
            <div className="text-sm text-neutral-400">
              <span className="text-neutral-500 font-medium">改进建议：</span>
              {overallEval.improvement_suggestion}
            </div>
          )}
        </div>
      )}

      {data.status === "in_progress" && (
        <div className="border border-sky-800 bg-sky-950 rounded-lg p-4 text-sm text-sky-300">
          面试尚未结束，数据可能不完整。
        </div>
      )}

      {data.status === "abandoned" && (
        <div className="border border-yellow-800 bg-yellow-950 rounded-lg p-4 text-sm text-yellow-300">
          面试未完成，无评估报告。
        </div>
      )}

      {/* Q/A Timeline */}
      <div className="space-y-4">
        <h2 className="text-sm font-semibold text-neutral-300">问答记录</h2>
        {sortedQuestions.length === 0 ? (
          <p className="text-neutral-500 text-sm">暂无问答记录</p>
        ) : (
          sortedQuestions.map((q, i) => {
            const ev = evalMap.get(q.id);
            return (
              <div key={q.id} className="border border-neutral-800 rounded-lg p-4 space-y-2">
                <div className="flex items-start gap-3">
                  <span className="text-xs text-sky-400 font-mono min-w-[24px]">Q{i + 1}</span>
                  <p className="text-sm text-neutral-200">{q.question_text}</p>
                  {q.question_audio_s3_key && (
                    <PlayButton interviewId={data.id} questionId={q.id} role="assistant" />
                  )}
                </div>
                {q.answer ? (
                  <div className="flex items-start gap-3 ml-1">
                    <span className="text-xs text-emerald-400 font-mono min-w-[24px]">A</span>
                    <div className="flex-1">
                      <p className="text-sm text-neutral-300">{q.answer.transcript_text}</p>
                      <span className="text-xs text-neutral-600">
                        {q.answer.duration_sec.toFixed(1)}s
                        {q.answer.user_audio_s3_key && (
                          <PlayButton interviewId={data.id} questionId={q.id} role="user" />
                        )}
                      </span>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-neutral-600 ml-8">未回答</p>
                )}
                {ev && (
                  <div className="ml-8 mt-2 border-t border-neutral-800 pt-2 space-y-1">
                    <div className="flex gap-4 text-xs">
                      <span className="text-neutral-500">
                        内容 <span className="text-neutral-300">{ev.content_score}</span>
                      </span>
                      <span className="text-neutral-500">
                        表达 <span className="text-neutral-300">{ev.expression_score}</span>
                      </span>
                    </div>
                    {ev.improvement_suggestion && (
                      <p className="text-xs text-neutral-400">💡 {ev.improvement_suggestion}</p>
                    )}
                    {ev.ideal_answer && (
                      <p className="text-xs text-neutral-500">📝 参考答案: {ev.ideal_answer}</p>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
