"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { base64FromInt16, int16FromBase64 } from "@/lib/audio-codec";

type TranscriptLine = {
  role: "user" | "assistant";
  text: string;
  final: boolean;
  ts: number; // epoch ms, set at first observation of this line
};

const WS_URL =
  process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/interview-demo";

function fmtTs(ms: number): string {
  const d = new Date(ms);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

// --- page ------------------------------------------------------------------
export default function InterviewDemoPage() {
  const [status, setStatus] = useState<"idle" | "connecting" | "live" | "error">("idle");
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [aiSpeaking, setAiSpeaking] = useState(false);
  const [micLevel, setMicLevel] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const playCursorRef = useRef<number>(0); // schedule-time cursor for seamless playback
  const aiSpeakingRef = useRef<boolean>(false); // avoid sending mic while AI is talking

  const appendTranscript = useCallback((line: TranscriptLine) => {
    setTranscript((prev) => {
      // Coalesce non-final partials per role; preserve the original ts of
      // the ongoing line so the UI timestamp is the moment that *line*
      // started, not the last partial update.
      const last = prev[prev.length - 1];
      if (last && last.role === line.role && !last.final && !line.final) {
        return [...prev.slice(0, -1), { ...line, ts: last.ts }];
      }
      if (last && last.role === line.role && !last.final && line.final) {
        return [...prev.slice(0, -1), { ...line, ts: last.ts }];
      }
      return [...prev, line];
    });
  }, []);

  const playPcm = useCallback((pcm: Int16Array) => {
    const ctx = audioCtxRef.current;
    if (!ctx) {
      console.warn("[audio] playPcm called with no AudioContext");
      return;
    }
    if (ctx.state === "suspended") {
      // Browsers may auto-suspend a context if created outside a user gesture.
      // Resume asynchronously; first frame may drop but subsequent frames play.
      ctx.resume().catch((e) => console.warn("[audio] resume failed:", e));
    }
    // Nova Sonic outputs 16kHz mono PCM16 — create an AudioBuffer at 16kHz
    const buffer = ctx.createBuffer(1, pcm.length, 16000);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) data[i] = pcm[i] / 32768;

    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);

    const now = ctx.currentTime;
    const startAt = Math.max(now, playCursorRef.current);
    src.start(startAt);
    playCursorRef.current = startAt + buffer.duration;
  }, []);

  const handleServerMessage = useCallback(
    (event: MessageEvent) => {
      let data: { type?: string; [k: string]: unknown };
      try {
        data = JSON.parse(event.data as string);
      } catch {
        return;
      }
      const type = data.type;
      if (type === "bidi_audio_stream" && typeof data.audio === "string") {
        playPcm(int16FromBase64(data.audio));
      } else if (type === "bidi_transcript_stream") {
        const role = (data.role === "user" ? "user" : "assistant") as "user" | "assistant";
        appendTranscript({
          role,
          text: typeof data.text === "string" ? data.text : "",
          final: data.is_final === true,
          ts: Date.now(),
        });
      } else if (type === "bidi_connection_start") {
        setStatus("live");
      } else if (type === "bidi_response_start") {
        aiSpeakingRef.current = true;
        setAiSpeaking(true);
      } else if (type === "bidi_response_complete" || type === "bidi_interruption") {
        aiSpeakingRef.current = false;
        setAiSpeaking(false);
      }
    },
    [appendTranscript, playPcm]
  );

  const start = useCallback(async () => {
    setError(null);
    setTranscript([]);
    setStatus("connecting");

    try {
      // 1) mic access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      micStreamRef.current = stream;

      // 2) audio context + worklet
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      playCursorRef.current = 0;
      // Critical: explicit resume inside the user-gesture-triggered click handler.
      // Without this, a 2nd start may land with state='suspended' and silently
      // schedule audio that never plays.
      if (ctx.state === "suspended") {
        await ctx.resume();
      }
      console.log("[audio] ctx state =", ctx.state, "sampleRate =", ctx.sampleRate);
      await ctx.audioWorklet.addModule("/pcm-worklet.js");
      const source = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, "pcm-capture-processor", {
        processorOptions: { inputRate: ctx.sampleRate },
      });
      workletNodeRef.current = node;

      // 3) WebSocket — connect BEFORE wiring the worklet, so we don't lose
      //    the first few PCM chunks while WS handshake is in flight.
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      // Mic-frame counter for diagnostics: lets us confirm in the browser
      // console that the worklet is emitting frames continuously (even when
      // the user is silent — VAD relies on seeing low-energy frames too).
      let micFrameCount = 0;

      // Bind worklet message handler FIRST, but guard by ws readyState.
      // We also always update the UI level meter (regardless of ws state).
      node.port.onmessage = (evt) => {
        const { pcm, level } = evt.data as { pcm: Int16Array; level: number };
        setMicLevel(level);
        if (ws.readyState !== WebSocket.OPEN) return;
        micFrameCount++;
        if (micFrameCount % 50 === 1) {
          // 50 frames ~= 5s @ 100ms/frame. Watch this in DevTools console.
          console.log(`[mic] sent ${micFrameCount} frames, last level=${level.toFixed(4)}`);
        }
        // Always stream mic to backend, even while AI is speaking.
        //
        // Why: Nova Sonic times out after 55s of no `audioInput` or
        // `interactive content` (ValidationException InternalErrorCode=532).
        // If we mute mic during AI speech, the quiet window (AI speaking +
        // user listening + thinking + hesitating) easily exceeds 55s.
        //
        // Echo/self-capture is handled by two layers:
        //   1. getUserMedia({ echoCancellation: true }) — browser AEC cancels
        //      speaker output picked up by the mic.
        //   2. Nova Sonic turn_detection — server-side VAD distinguishes
        //      real user interruption from AI's own echo.
        //
        // The Twilio reference integration (sample-amazon-nova-sonic-twilio-
        // integration/src/server.ts) also forwards every audio frame
        // unconditionally; we match that behavior.
        ws.send(
          JSON.stringify({
            type: "bidi_audio_input",
            audio: base64FromInt16(pcm),
            format: "pcm",
            sample_rate: 16000,
            channels: 1,
          })
        );
      };

      ws.onopen = () => {
        console.log("[ws] open; mic will start streaming");
        // Only NOW wire mic -> worklet, so worklet doesn't run before we're
        // ready to forward. This avoids silently dropping the first seconds
        // of mic audio during WS handshake.
        source.connect(node);
      };
      ws.onmessage = handleServerMessage;
      ws.onerror = () => {
        setError("WebSocket error");
        setStatus("error");
      };
      ws.onclose = () => {
        setStatus((s) => (s === "live" ? "idle" : s));
      };
      // mic -> worklet wiring happens in ws.onopen above (once socket is ready)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setStatus("error");
    }
  }, [handleServerMessage]);

  const stop = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    workletNodeRef.current?.disconnect();
    workletNodeRef.current = null;
    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;
    audioCtxRef.current?.close().catch(() => undefined);
    audioCtxRef.current = null;
    playCursorRef.current = 0;
    aiSpeakingRef.current = false;
    setAiSpeaking(false);
    setMicLevel(0);
    setStatus("idle");
  }, []);

  useEffect(() => () => stop(), [stop]);

  const live = status === "live" || status === "connecting";

  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col items-center p-6">
      <div className="max-w-2xl w-full">
        <h1 className="text-2xl font-semibold mb-1">AI 模拟面试</h1>
        <p className="text-neutral-400 text-sm mb-6">
          华为 · 硬件技术工程师（射频技术方向）实习生
        </p>

        <div className="flex gap-3 mb-4 items-center">
          {!live ? (
            <button
              onClick={start}
              className="px-5 py-2 rounded-md bg-emerald-600 hover:bg-emerald-500 font-medium"
            >
              开始面试
            </button>
          ) : (
            <button
              onClick={stop}
              className="px-5 py-2 rounded-md bg-red-600 hover:bg-red-500 font-medium"
            >
              结束面试
            </button>
          )}
          <a
            href="/history"
            className="px-4 py-2 rounded-md border border-neutral-700 text-neutral-400 hover:text-neutral-200 hover:border-neutral-500 text-sm"
          >
            查看历史
          </a>
          <div className="flex items-center gap-2 text-sm text-neutral-400">
            <span
              className={`inline-block w-2 h-2 rounded-full ${
                status === "live"
                  ? "bg-emerald-500 animate-pulse"
                  : status === "connecting"
                    ? "bg-yellow-500"
                    : status === "error"
                      ? "bg-red-500"
                      : "bg-neutral-600"
              }`}
            />
            {status === "idle" && "待机"}
            {status === "connecting" && "连接中..."}
            {status === "live" && (aiSpeaking ? "面试官说话中" : "请回答")}
            {status === "error" && "出错了"}
          </div>
        </div>

        {/* Mic level meter (only visible when live) */}
        {live && (
          <div className="mb-4">
            <div className="flex items-center gap-2">
              <span className="text-xs text-neutral-500 w-12">麦克风</span>
              <div className="flex-1 h-2 bg-neutral-800 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-75 ${
                    aiSpeaking ? "bg-neutral-700" : "bg-emerald-500"
                  }`}
                  style={{
                    // level is RMS in [0, ~0.5]; amplify + clamp
                    width: `${Math.min(100, Math.round(micLevel * 400))}%`,
                  }}
                />
              </div>
              <span className="text-xs text-neutral-600 w-16 text-right">
                {aiSpeaking ? "已静音" : "采集中"}
              </span>
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 text-sm text-red-400 bg-red-950/40 border border-red-900 rounded px-3 py-2">
            {error}
          </div>
        )}

        <div className="bg-neutral-900 border border-neutral-800 rounded-lg p-4 min-h-[300px] space-y-3">
          {transcript.length === 0 && (
            <p className="text-neutral-500 text-sm italic">
              点击"开始面试"后，允许麦克风权限，面试官会主动打招呼并提第一题。
            </p>
          )}
          {transcript.map((line, i) => (
            <div key={i} className="flex gap-3">
              <span className="text-xs mt-1 text-neutral-500 font-mono min-w-[64px] tabular-nums">
                {fmtTs(line.ts)}
              </span>
              <span
                className={`text-xs mt-1 ${
                  line.role === "assistant" ? "text-sky-400" : "text-emerald-400"
                } min-w-[56px]`}
              >
                {line.role === "assistant" ? "面试官" : "我"}
              </span>
              <span
                className={`text-sm ${line.final ? "text-neutral-200" : "text-neutral-400 italic"}`}
              >
                {line.text}
                {!line.final && "…"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </main>
  );
}
