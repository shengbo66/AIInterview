"""Sprint 2: WS endpoint + persistence via BidiInterviewSession.

Scope:
  - 1 WebSocket path /ws/interview-demo
  - Huawei + RF Intern hardcoded (role_title constant)
  - system_prompt composed from seeded Huawei CompanyStyle
  - Interview/Question/Answer persisted as transcripts arrive
  - AI audio uploaded to S3 per turn (user audio upload: later sprint)

Performance note:
  Strands' event loop forwards one event per `send()` call. If send does heavy
  work (S3 upload, DB commit) synchronously, subsequent events back up — audio
  frames get delayed and the whole conversation stalls. So we:
    1. Always forward to the browser FIRST (keeps audio latency low)
    2. Dispatch persistence to a background task (fire-and-forget)
    3. Track background tasks so we can flush them on session close

Bootstrap note:
  Nova Sonic NEVER speaks first on its own. This is by design — the model
  waits for user audio to trigger a response. Without a bootstrap utterance,
  the session hits Sonic's internal 55s "no audio" timeout.

  Reference: Twilio Nova Sonic integration sample
  (sample-amazon-nova-sonic-twilio-integration/src/server.ts) does the same
  thing: "send the audio bytes that say 'hello' as to mimic the user
  greeting to allow model to speak first".

  We inject a pre-recorded "Hello" PCM (assets/hello.pcm) right after Strands
  opens the audio content, so Sonic generates a greeting + first question.
"""
import asyncio
import base64
import contextlib
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from strands.experimental.bidi import BidiAgent
from strands.experimental.bidi.models import BidiNovaSonicModel

from app.config import settings
from app.db import SessionLocal
from app.services.bidi_interview_session import BidiInterviewSession

logger = logging.getLogger("interviewer.demo_bidi")

router = APIRouter(tags=["demo"])

# Locked for Sprint 2 — only this role, only Huawei style (seeded in unit-1).
ROLE_TITLE = "硬件技术工程师（射频技术方向）实习生"

# Bootstrap audio path (relative to backend/)
_HELLO_PCM_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "hello.pcm"


def _load_hello_pcm() -> bytes | None:
    """Pre-load the bootstrap greeting PCM. Returns None if missing."""
    try:
        if _HELLO_PCM_PATH.exists():
            data = _HELLO_PCM_PATH.read_bytes()
            logger.info("loaded hello.pcm: %d bytes (%.2fs)", len(data), len(data) / 32000)
            return data
    except Exception:
        logger.exception("failed to load hello.pcm")
    logger.warning("hello.pcm not found at %s — Sonic may not greet first", _HELLO_PCM_PATH)
    return None


_HELLO_PCM = _load_hello_pcm()
_HELLO_CHUNK_MS = 100  # stream it as 100ms chunks, same shape as browser
_HELLO_CHUNK_BYTES = 16000 * _HELLO_CHUNK_MS // 1000 * 2  # 3200 bytes per chunk


async def _persist_safe(session: BidiInterviewSession, event: dict) -> None:
    """Swallow persistence errors so they don't crash the WS session."""
    try:
        await session.on_event(event)
    except Exception:
        logger.exception(
            "BACKGROUND persist failed type=%s (caught, session continues)",
            event.get("type"),
        )


def _build_agent(system_prompt: str) -> BidiAgent:
    model = BidiNovaSonicModel(
        model_id=settings.nova_sonic_model_id,
        provider_config={
            "audio": {
                "voice": "tiffany",
                "input_rate": 16000,
                "output_rate": 16000,
                "channels": 1,
                "format": "pcm",
            },
            "inference": {},
            # CRITICAL: Nova Sonic V2 needs server-side turn detection enabled,
            # otherwise it waits indefinitely for an explicit contentEnd event
            # and hits its internal 55s "no audio" timeout, killing the session.
            "turn_detection": {
                "endpointingSensitivity": "MEDIUM",
            },
        },
        client_config={"region": settings.aws_region},
    )
    return BidiAgent(model=model, tools=[], system_prompt=system_prompt)


@router.websocket("/ws/interview-demo")
async def interview_demo(websocket: WebSocket) -> None:
    """Hardcoded Huawei RF Intern interview, persisted via BidiInterviewSession."""
    await websocket.accept()
    logger.info("WS demo connected at %s", datetime.now().isoformat())

    session = BidiInterviewSession(SessionLocal, role_title=ROLE_TITLE)
    try:
        await session.setup()
    except Exception:
        logger.exception("session setup failed")
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "code": "setup_failed"})
        with contextlib.suppress(Exception):
            await websocket.close()
        return

    agent = _build_agent(session.system_prompt)

    with contextlib.suppress(Exception):
        await websocket.send_json({"type": "session_ready", "interview_id": session.interview_id})

    pending_tasks: set[asyncio.Task] = set()

    recv_count = {"audio": 0, "other": 0}

    # Build the bootstrap queue: break hello.pcm into 100ms chunks and
    # yield them BEFORE we start reading from the real WS. This makes Sonic
    # think the user said "hello" right at the start of the session, which
    # triggers the model to greet back + ask the first question.
    # Reference: Twilio sample does the exact same thing.
    bootstrap_queue: list[dict] = []
    if _HELLO_PCM:
        for i in range(0, len(_HELLO_PCM), _HELLO_CHUNK_BYTES):
            chunk = _HELLO_PCM[i:i + _HELLO_CHUNK_BYTES]
            # zero-pad last chunk so every frame is 100ms
            if len(chunk) < _HELLO_CHUNK_BYTES:
                chunk = chunk + b"\x00" * (_HELLO_CHUNK_BYTES - len(chunk))
            bootstrap_queue.append({
                "type": "bidi_audio_input",
                "audio": base64.b64encode(chunk).decode(),
                "format": "pcm",
                "sample_rate": 16000,
                "channels": 1,
            })
        logger.info("bootstrap queued %d hello chunks", len(bootstrap_queue))

    async def recv():
        """Pulled by Strands; forward one client message per call.

        Also: buffer user PCM into the session for later S3 upload.

        Emits bootstrap hello chunks BEFORE touching the WS, so Sonic gets
        user-like audio and responds (Sonic never speaks first on its own).
        """
        # Drain bootstrap first, pacing at 100ms per chunk (realtime).
        if bootstrap_queue:
            msg = bootstrap_queue.pop(0)
            await asyncio.sleep(_HELLO_CHUNK_MS / 1000.0)
            return msg

        try:
            data = await websocket.receive_json()
        except WebSocketDisconnect:
            # Propagate so agent.run exits cleanly
            logger.info("recv: client disconnected")
            raise
        except Exception:
            logger.exception("recv: unexpected error reading WS")
            raise
        if isinstance(data, dict) and data.get("type") == "bidi_audio_input":
            recv_count["audio"] += 1
            if recv_count["audio"] % 20 == 1:
                logger.info("RECV bidi_audio_input count=%d", recv_count["audio"])
            b64 = data.get("audio")
            if isinstance(b64, str):
                try:
                    session.append_user_audio(base64.b64decode(b64))
                except Exception:
                    logger.debug("bad user audio b64", exc_info=True)
        else:
            recv_count["other"] += 1
            logger.info("RECV non-audio type=%s", data.get("type") if isinstance(data, dict) else "?")
        return data

    async def send(event):
        """Forward to browser FIRST; persist in background to not block audio.

        WS send failures are swallowed (logged only). Raising here would
        propagate into `agent.run`'s output task, cancel the whole _TaskGroup,
        and kill an otherwise-recoverable Strands session. In particular,
        Strands auto-restarts Nova Sonic on `BidiConnectionRestartEvent`
        (triggered by Nova's 175s internal timeout) — we must not abort that
        recovery path just because the browser's WS is momentarily unhealthy.

        The browser will simply not receive this event; persistence is
        scheduled independently and is not affected.
        """
        event_dict = event if isinstance(event, dict) else dict(event)
        ev_type = event_dict.get("type")
        if ev_type != "bidi_audio_stream":
            logger.info("SEND event type=%s", ev_type)
        try:
            await websocket.send_json(event_dict)
        except Exception:
            # Don't re-raise: keep the Strands session alive even if the
            # browser hangs up or the WS is in a transient bad state.
            logger.warning(
                "ws.send_json failed type=%s (swallowed to keep session alive)",
                ev_type,
            )
        task = asyncio.create_task(_persist_safe(session, event_dict))
        pending_tasks.add(task)
        task.add_done_callback(pending_tasks.discard)

    try:
        await agent.run(inputs=[recv], outputs=[send], invocation_state={})
        logger.info("agent.run() returned NORMALLY (script ended / Sonic closed)")
    except WebSocketDisconnect:
        logger.info("client disconnected (WebSocketDisconnect)")
    except Exception:
        logger.exception("agent.run raised an exception — this is why the session ended")
    finally:
        # Drain pending persistence tasks so we don't lose the last turn.
        if pending_tasks:
            logger.info("flushing %d pending persistence tasks", len(pending_tasks))
            done, not_done = await asyncio.wait(pending_tasks, timeout=10.0)
            if not_done:
                logger.error(
                    "TIMEOUT flushing persistence: %d tasks still pending after 10s; data loss likely",
                    len(not_done),
                )
            # log any task exceptions that slipped through
            for t in done:
                exc = t.exception()
                if exc is not None:
                    logger.error("pending task ended with exception: %r", exc)
        await session.finalize_safe(status="completed")
        with contextlib.suppress(Exception):
            await agent.stop()
        with contextlib.suppress(Exception):
            await websocket.close()
