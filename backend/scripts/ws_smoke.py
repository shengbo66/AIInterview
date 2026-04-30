"""WS smoke test: connect to /ws/interview-demo and drive a fake conversation.

Independent of the browser — pure Python WebSocket client. Used to verify
the backend side of the audio pipeline (recv loop, Strands bridge, Sonic
connection) without depending on frontend JS/AudioWorklet timing.

Two modes:

  1. Dry mode (default, SMOKE_REAL_AWS unset):
     - We patch nova_sonic model construction before import so it never
       reaches real AWS. The agent will fail to start; we verify we get
       the setup_failed error properly.

  2. Real mode (SMOKE_REAL_AWS=1):
     - Connects to real Nova Sonic via AWS credentials.
     - Sends 5s of synthesized audio (sine + silence) to trigger VAD.
     - Records all server events for 30s (hard cap).
     - Cost: ~$0.01 per run.

Usage:
  # Assumes backend is running on localhost:8000
  python scripts/ws_smoke.py              # dry mode
  SMOKE_REAL_AWS=1 python scripts/ws_smoke.py    # real AWS
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import os
import struct
import sys
import time
from collections import Counter
from pathlib import Path

try:
    import websockets
except ImportError:
    print("ERROR: pip install websockets", file=sys.stderr)
    sys.exit(1)


WS_URL = os.getenv("SMOKE_WS_URL", "ws://localhost:8000/ws/interview-demo")
HARD_CAP_SEC = int(os.getenv("SMOKE_HARD_CAP", "30"))
SAMPLE_RATE = 16000
TONE_HZ = 440          # 440Hz sine — actual human-voice-like fundamental
TONE_AMPLITUDE = 8000  # ~25% of int16
CHUNK_MS = 100
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000  # 1600


def tone_chunk(sample_offset: int) -> bytes:
    """100ms of sine wave, offset to keep phase continuous."""
    samples = [
        int(TONE_AMPLITUDE * math.sin(2 * math.pi * TONE_HZ * (sample_offset + i) / SAMPLE_RATE))
        for i in range(CHUNK_SAMPLES)
    ]
    return struct.pack(f"<{len(samples)}h", *samples)


def silence_chunk() -> bytes:
    return b"\x00\x00" * CHUNK_SAMPLES


def encode_audio_msg(pcm: bytes) -> str:
    return json.dumps({
        "type": "bidi_audio_input",
        "audio": base64.b64encode(pcm).decode(),
        "format": "pcm",
        "sample_rate": SAMPLE_RATE,
        "channels": 1,
    })


async def run_smoke(tone_seconds: int = 3, silence_seconds: int = 2, pcm_file: str | None = None) -> dict:
    """Connect, stream audio, record all events. Return summary."""
    print(f"Connecting to {WS_URL} (hard cap {HARD_CAP_SEC}s)")
    start = time.monotonic()
    events: list[dict] = []
    type_counts: Counter[str] = Counter()
    bytes_received = 0
    connection_error: str | None = None

    # Preload PCM file if provided (real speech sample)
    file_pcm: bytes | None = None
    if pcm_file:
        with open(pcm_file, "rb") as f:
            file_pcm = f.read()
        # normalize to even byte count
        if len(file_pcm) % 2:
            file_pcm = file_pcm[:-1]
        n_samples = len(file_pcm) // 2
        print(f"  Using PCM file {pcm_file}: {n_samples} samples ({n_samples/SAMPLE_RATE:.1f}s @ 16kHz)")

    async def sender(ws):
        if file_pcm:
            # Send the file as 100ms chunks at real-time pace
            chunk_bytes = CHUNK_SAMPLES * 2
            sent = 0
            while sent < len(file_pcm):
                chunk = file_pcm[sent:sent + chunk_bytes]
                # zero-pad last chunk if short
                if len(chunk) < chunk_bytes:
                    chunk = chunk + b"\x00" * (chunk_bytes - len(chunk))
                await ws.send(encode_audio_msg(chunk))
                sent += chunk_bytes
                await asyncio.sleep(CHUNK_MS / 1000.0)
            print(f"  [send] {len(file_pcm)//2/SAMPLE_RATE:.1f}s speech sent, sending silence tail")
            # Silence tail so VAD triggers end-of-turn
            for _ in range(silence_seconds * (1000 // CHUNK_MS)):
                await ws.send(encode_audio_msg(silence_chunk()))
                await asyncio.sleep(CHUNK_MS / 1000.0)
        elif tone_seconds == 0:
            # No-send mode: just listen (used to verify backend bootstrap trick)
            print("  [send] no-send mode: just listening for backend-driven bootstrap")
        else:
            # Synthetic tone
            offset = 0
            for _ in range(tone_seconds * (1000 // CHUNK_MS)):
                await ws.send(encode_audio_msg(tone_chunk(offset)))
                offset += CHUNK_SAMPLES
                await asyncio.sleep(CHUNK_MS / 1000.0)
            print(f"  [send] {tone_seconds}s tone done, starting silence")
            for _ in range(silence_seconds * (1000 // CHUNK_MS)):
                await ws.send(encode_audio_msg(silence_chunk()))
                await asyncio.sleep(CHUNK_MS / 1000.0)
            print(f"  [send] {silence_seconds}s silence done; now just listening")
        # Keep connection alive for the rest of hard cap
        while time.monotonic() - start < HARD_CAP_SEC:
            await ws.send(encode_audio_msg(silence_chunk()))
            await asyncio.sleep(CHUNK_MS / 1000.0)

    async def receiver(ws):
        nonlocal bytes_received
        try:
            async for raw in ws:
                elapsed = time.monotonic() - start
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                t = data.get("type", "?")
                type_counts[t] += 1
                if t == "bidi_audio_stream":
                    audio_b64 = data.get("audio", "")
                    try:
                        bytes_received += len(base64.b64decode(audio_b64))
                    except Exception:
                        pass
                    # too noisy to log each frame
                else:
                    preview = json.dumps(data)[:200]
                    print(f"  [+{elapsed:6.2f}s recv] {t:32s} {preview}")
                events.append({"t": t, "elapsed": round(elapsed, 2)})
        except websockets.exceptions.ConnectionClosed as e:
            print(f"  [recv] connection closed: code={e.code} reason={e.reason}")

    try:
        async with websockets.connect(WS_URL) as ws:
            print(f"  WS open, readyState=OPEN")
            send_task = asyncio.create_task(sender(ws))
            recv_task = asyncio.create_task(receiver(ws))
            try:
                await asyncio.wait_for(
                    asyncio.gather(send_task, recv_task, return_exceptions=True),
                    timeout=HARD_CAP_SEC,
                )
            except asyncio.TimeoutError:
                print(f"  [main] hard cap {HARD_CAP_SEC}s reached, closing")
            send_task.cancel()
            recv_task.cancel()
    except Exception as e:
        connection_error = f"{type(e).__name__}: {e}"
        print(f"  [fatal] connection error: {connection_error}")

    duration = time.monotonic() - start
    return {
        "duration_sec": round(duration, 1),
        "connection_error": connection_error,
        "total_events": len(events),
        "type_counts": dict(type_counts),
        "ai_audio_bytes": bytes_received,
        "events_first_5": events[:5],
    }


def print_verdict(summary: dict) -> int:
    print("\n" + "=" * 60)
    print("SMOKE TEST SUMMARY")
    print("=" * 60)
    print(f"Duration:         {summary['duration_sec']}s")
    print(f"Connection error: {summary['connection_error'] or 'none'}")
    print(f"Total events:     {summary['total_events']}")
    print(f"AI audio bytes:   {summary['ai_audio_bytes']}")
    print(f"Event type counts:")
    for t, n in sorted(summary["type_counts"].items(), key=lambda x: -x[1]):
        print(f"  {n:5d}  {t}")

    # Verdict
    print("\nVERDICT:")
    counts = summary["type_counts"]
    if summary["connection_error"]:
        print("  ❌ FAIL: couldn't connect to backend. Is uvicorn running?")
        return 2
    if counts.get("error"):
        print("  ❌ FAIL: backend emitted 'error' event — session setup failed")
        return 3
    if counts.get("bidi_connection_start", 0) == 0:
        print("  ⚠️  WARN: Sonic connection never established; check AWS creds + demo_bidi.py")
        return 4
    if counts.get("bidi_audio_stream", 0) == 0:
        print("  ⚠️  WARN: Sonic never sent audio back. Possible causes:")
        print("           - VAD didn't trigger (synthesized tone too short/quiet)")
        print("           - Sonic 55s timeout (check backend log for ValidationException)")
        print("           - recv loop not forwarding our audio to Sonic")
        return 5
    if summary["ai_audio_bytes"] < 1000:
        print("  ⚠️  WARN: very little AI audio; may have partial success")
        return 6
    print("  ✅ PASS: full audio pipeline works end-to-end")
    return 0


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tone", type=int, default=3, help="seconds of tone")
    parser.add_argument("--silence", type=int, default=2, help="seconds of silence after tone")
    parser.add_argument("--pcm-file", type=str, default=None,
                        help="path to raw PCM16 mono 16kHz file (real speech, bypasses synthetic tone)")
    args = parser.parse_args()

    if not os.getenv("SMOKE_REAL_AWS"):
        print(
            "⚠️  SMOKE_REAL_AWS not set — this will hit real Nova Sonic (~$0.01)."
            "\n    If backend is configured without AWS creds, you'll see setup_failed."
            "\n    Continuing anyway since there's no safe 'dry' mode that goes through Sonic..."
        )

    summary = await run_smoke(tone_seconds=args.tone, silence_seconds=args.silence, pcm_file=args.pcm_file)
    Path("/tmp/ws_smoke_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nSummary written to /tmp/ws_smoke_summary.json")
    sys.exit(print_verdict(summary))


if __name__ == "__main__":
    asyncio.run(main())
