"""Probe: capture all Strands BidiAgent event types + token usage.

Goal (one run, ~20-30 sec, ~$0.005):
  1. Start a local BidiAgent session (no WebSocket, direct in-process)
  2. Feed ~5s of silence PCM to trigger Sonic's greeting / response
  3. Record every event emitted by `outputs`, including type + payload shape
  4. Specifically hunt for: token usage, transcription completion events
  5. Write all findings to strands-events.md

Usage:
  cd nova-sonic-poc
  source .venv/bin/activate
  python probe_events.py

Output:
  - Console: real-time event stream
  - ./strands-events.md: structured report for unit-2 design
"""
import asyncio
import base64
import json
import math
import os
import struct
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from strands.experimental.bidi import BidiAgent
from strands.experimental.bidi.models import BidiNovaSonicModel

load_dotenv(override=True)

MODEL_ID = os.getenv("MODEL_ID", "amazon.nova-2-sonic-v1:0")
REGION = os.getenv("BEDROCK_REGION", "us-east-1")
RUN_SECONDS = 30  # total probe duration (hard cap)

# ---- Generate an actual audio signal Sonic will detect as speech ----
# Nova Sonic uses VAD — silent PCM or text-only won't trigger voice output.
# We fake a voiced segment with a 1kHz sine wave for 2s, then silence
# so Sonic sees an "end of turn" and responds.
SAMPLE_RATE = 16000
AMPLITUDE = 10000  # ~30% of int16 range (loud enough to trigger VAD)


def _tone_chunk_100ms(start_sample: int) -> bytes:
    """100ms of 1kHz sine wave at 16kHz mono PCM16."""
    samples = []
    for i in range(1600):
        n = start_sample + i
        value = int(AMPLITUDE * math.sin(2 * math.pi * 1000 * n / SAMPLE_RATE))
        samples.append(value)
    return struct.pack(f"<{len(samples)}h", *samples)


SILENCE_CHUNK_100MS = b"\x00\x00" * 1600


def shape_of(v, depth=0):
    """Return a compact schema description for a JSON-ish value."""
    if depth > 3:
        return "..."
    if isinstance(v, dict):
        return {k: shape_of(vv, depth + 1) for k, vv in list(v.items())[:20]}
    if isinstance(v, list):
        if not v:
            return []
        return [shape_of(v[0], depth + 1), f"<len={len(v)}>"]
    if isinstance(v, str):
        if len(v) > 60:
            return f"str<{len(v)}>"
        return f'"{v}"'
    if isinstance(v, (int, float, bool)) or v is None:
        return type(v).__name__ if not isinstance(v, bool) else str(v)
    if isinstance(v, bytes):
        return f"bytes<{len(v)}>"
    return type(v).__name__


async def main():
    print(f"Model: {MODEL_ID}  Region: {REGION}")
    print(f"Probe duration: up to {RUN_SECONDS}s")

    model = BidiNovaSonicModel(
        model_id=MODEL_ID,
        provider_config={
            "audio": {"voice": "tiffany", "input_rate": 16000, "output_rate": 16000,
                      "channels": 1, "format": "pcm"},
            "inference": {},
        },
        client_config={"region": REGION},
    )
    agent = BidiAgent(
        model=model,
        tools=[],
        system_prompt="You are a friendly assistant. Say hello in one short sentence, then wait.",
    )

    # -- observability ------------------------------------------------------
    events_seen: list[dict] = []            # full event list
    type_counts: Counter = Counter()        # type → count
    shape_samples: dict[str, dict] = {}     # type → first-seen shape
    usage_hits: list[dict] = []             # anything that looks like usage
    ai_audio_bytes = 0
    start_ts = datetime.now()

    # -- inputs: 2s of 1kHz tone, then 3s silence (triggers VAD end-of-turn) -
    # Schedule: emit one 100ms chunk every real 100ms so Sonic perceives
    # timing naturally. Feed from a queue to decouple schedule from recv.
    input_queue: asyncio.Queue = asyncio.Queue()

    async def feeder():
        # 2s of tone
        for i in range(20):
            chunk = _tone_chunk_100ms(i * 1600)
            await input_queue.put({
                "type": "bidi_audio_input",
                "audio": base64.b64encode(chunk).decode(),
                "format": "pcm",
                "sample_rate": SAMPLE_RATE,
                "channels": 1,
            })
            await asyncio.sleep(0.1)
        # 3s of silence → tells VAD "user stopped speaking"
        for _ in range(30):
            await input_queue.put({
                "type": "bidi_audio_input",
                "audio": base64.b64encode(SILENCE_CHUNK_100MS).decode(),
                "format": "pcm",
                "sample_rate": SAMPLE_RATE,
                "channels": 1,
            })
            await asyncio.sleep(0.1)
        # Sentinel so recv() knows to block
        await input_queue.put(None)

    feeder_task = asyncio.create_task(feeder())

    async def recv():
        msg = await input_queue.get()
        if msg is None:
            # No more audio; block for outputs to stream back
            await asyncio.sleep(RUN_SECONDS + 5)
        return msg

    async def send(data):
        nonlocal ai_audio_bytes
        elapsed = (datetime.now() - start_ts).total_seconds()
        if isinstance(data, dict):
            t = data.get("type", "<no-type>")
        else:
            t = f"<non-dict:{type(data).__name__}>"
            data = {"_raw_type": type(data).__name__, "_repr": repr(data)[:200]}

        type_counts[t] += 1
        if t not in shape_samples:
            shape_samples[t] = shape_of(data)

        # track AI audio bytes
        if t == "bidi_audio_stream" and isinstance(data.get("audio"), str):
            try:
                ai_audio_bytes += len(base64.b64decode(data["audio"]))
            except Exception:
                pass

        # hunt for usage info (case-insensitive key scan)
        def scan_usage(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    low = k.lower()
                    if any(x in low for x in ("usage", "token", "cost", "input_token", "output_token")):
                        usage_hits.append({"path": path + "." + k, "value": v, "event_type": t})
                    scan_usage(v, path + "." + k)
            elif isinstance(obj, list):
                for i, v in enumerate(obj[:5]):
                    scan_usage(v, path + f"[{i}]")

        scan_usage(data)

        events_seen.append({"t": t, "elapsed": round(elapsed, 2), "data": data})

        # console: skip noisy audio frames
        if t != "bidi_audio_stream":
            preview = json.dumps(data, default=str)[:200]
            print(f"[+{elapsed:6.2f}s] {t:40s} {preview}")

    # -- run ----------------------------------------------------------------
    # Strategy: spawn run() as a task; stop it cleanly either by feed() ending
    # (which ends recv, which ends inputs task) or by hard timeout.
    run_task = asyncio.create_task(
        agent.run(inputs=[recv], outputs=[send], invocation_state={})
    )
    try:
        await asyncio.wait_for(asyncio.shield(run_task), timeout=RUN_SECONDS)
    except asyncio.TimeoutError:
        print(f"\n[probe] hard timeout at {RUN_SECONDS}s, stopping agent")
    except Exception as e:
        print(f"\n[probe] run raised: {type(e).__name__}: {e}")
    finally:
        # ask agent to stop; tolerate cascading cancellations
        try:
            await asyncio.wait_for(agent.stop(), timeout=3.0)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as e:
            print(f"[probe] agent.stop() ignored: {type(e).__name__}: {e}")
        if not run_task.done():
            run_task.cancel()
            try:
                await run_task
            except (asyncio.CancelledError, Exception):
                pass
        if not feeder_task.done():
            feeder_task.cancel()
            try:
                await feeder_task
            except (asyncio.CancelledError, Exception):
                pass

    # -- report -------------------------------------------------------------
    duration = (datetime.now() - start_ts).total_seconds()
    print(f"\n===== Probe summary =====")
    print(f"Duration: {duration:.1f}s   Total events: {len(events_seen)}")
    print(f"AI audio received: {ai_audio_bytes} bytes (~{ai_audio_bytes/32000:.1f}s at 16kHz PCM16)")
    print(f"Event types:")
    for t, n in type_counts.most_common():
        print(f"  {n:5d}  {t}")
    print(f"\nUsage-like fields found: {len(usage_hits)}")
    for h in usage_hits[:20]:
        print(f"  {h['event_type']}{h['path']} = {h['value']}")

    # -- write markdown -----------------------------------------------------
    out = Path("strands-events.md")
    lines = [
        "# Strands BidiAgent Event Probe",
        "",
        f"- Date: {datetime.now().isoformat()}",
        f"- Model: `{MODEL_ID}`",
        f"- Region: `{REGION}`",
        f"- Probe duration: {duration:.1f}s",
        f"- Total events: {len(events_seen)}",
        f"- AI audio bytes: {ai_audio_bytes} (~{ai_audio_bytes/32000:.1f}s)",
        "",
        "## Event type counts",
        "",
        "| Type | Count |",
        "|---|---|",
    ]
    for t, n in type_counts.most_common():
        lines.append(f"| `{t}` | {n} |")
    lines.extend([
        "",
        "## First-seen payload shape per type",
        "",
    ])
    for t, shape in shape_samples.items():
        lines.append(f"### `{t}`")
        lines.append("```json")
        lines.append(json.dumps(shape, indent=2, default=str))
        lines.append("```")
        lines.append("")

    lines.extend([
        "## Usage / token / cost hits",
        "",
    ])
    if usage_hits:
        lines.append("| Event type | Path | Value |")
        lines.append("|---|---|---|")
        for h in usage_hits:
            v = str(h["value"])[:80]
            lines.append(f"| `{h['event_type']}` | `{h['path']}` | `{v}` |")
    else:
        lines.append("**No usage-like fields found.** Recommend pricing-by-duration fallback.")

    lines.extend([
        "",
        "## Full event timeline (non-audio)",
        "",
        "```",
    ])
    for e in events_seen:
        if e["t"] == "bidi_audio_stream":
            continue
        preview = json.dumps(e["data"], default=str)[:200]
        lines.append(f"[+{e['elapsed']:6.2f}s] {e['t']:40s} {preview}")
    lines.append("```")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✓ Report written to {out.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
