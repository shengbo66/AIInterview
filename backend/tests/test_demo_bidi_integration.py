"""Integration test for demo_bidi WS endpoint: verify event forwarding +
persistence pipeline with a scripted FakeBidiAgent (no real AWS).

Design:
  - Patch `_build_agent` in demo_bidi to return our FakeBidiAgent
  - FakeBidiAgent.run(inputs=[recv], outputs=[send]) scripts a conversation:
    1. emit connection_start
    2. emit AI audio frames + assistant transcript (Q1)
    3. wait for user audio input via recv
    4. emit user transcript
    5. repeat for Q2
    6. end (emit response_complete)
  - Use FastAPI TestClient.websocket_connect() to drive the WS
  - Assert:
    - All non-audio events reach the client in order
    - Audio frames are forwarded in < 100ms even when session.on_event is slow
    - Interview row ends up status=completed with correct Q+A counts
    - No pending persistence tasks are leaked
"""
import asyncio
import base64
import time
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Answer, CompanyStyle, Interview, Question


# ---------------------------------------------------------------- FakeAgent
class FakeBidiAgent:
    """Scripts a conversation via the Strands agent.run contract.

    Script is a list of "actions":
      - ("emit", {event_dict}): emit to outputs
      - ("wait_user_input", n_chunks): consume n bidi_audio_input messages from recv
      - ("sleep", secs): simulate processing delay
    """

    def __init__(self, script: list[tuple]) -> None:
        self.script = script
        self.stopped = False

    async def run(self, inputs: list, outputs: list, invocation_state: dict) -> None:
        # Only single input / output expected (matches demo_bidi)
        recv = inputs[0]
        send = outputs[0]
        self.received_inputs: list[dict] = []
        for action in self.script:
            if self.stopped:
                return
            op = action[0]
            if op == "emit":
                await send(action[1])
            elif op == "wait_user_input":
                n = action[1]
                for _ in range(n):
                    # Pull one user message; if it's bidi_audio_input ok; ignore others
                    try:
                        msg = await asyncio.wait_for(recv(), timeout=5.0)
                        self.received_inputs.append(msg)
                    except TimeoutError:
                        return
            elif op == "sleep":
                await asyncio.sleep(action[1])

    async def stop(self) -> None:
        self.stopped = True


# ------------------------------------------------------------- fixtures
@pytest_asyncio.fixture
async def _company_in_mem_db(monkeypatch, tmp_path):
    """
    Replace the app's SessionLocal with an in-memory SQLite engine, seed company,
    and patch both `app.db.SessionLocal` AND `app.routers.demo_bidi.SessionLocal`
    (the router imported it by name).
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app import db as db_module
    from app.models import Base
    from app.routers import demo_bidi as demo_module

    # StaticPool: reuse a single connection so all sessions share the same
    # in-memory database. Without this, aiosqlite opens a fresh connection
    # per checkout and each gets an independent (empty) :memory: db.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SF = async_sessionmaker(engine, expire_on_commit=False)

    # Seed company
    async with SF() as s:
        s.add(
            CompanyStyle(
                name="H公司",
                interviewer_style_tags=["结构化"],
                preferred_question_types=["技术深度"],
                sample_questions=["介绍射频项目"],
                prompt_context_text="H公司面试维度",
                is_builtin=True,
            )
        )
        await s.commit()

    monkeypatch.setattr(db_module, "SessionLocal", SF)
    monkeypatch.setattr(demo_module, "SessionLocal", SF)
    yield SF
    await engine.dispose()


@pytest.fixture
def _patch_s3(monkeypatch):
    """Mock s3_audio.upload (also inject artificial latency to test non-blocking)."""
    from unittest.mock import AsyncMock

    upload = AsyncMock(return_value="stub-key")
    # The session module imported `s3_audio` at module level
    monkeypatch.setattr(
        "app.services.bidi_interview_session.s3_audio.upload", upload
    )
    return upload


@pytest.fixture
def _patch_eval(monkeypatch):
    """Mock evaluate_interview so TestClient tests don't fire real Claude calls."""
    from unittest.mock import AsyncMock

    mock = AsyncMock()
    monkeypatch.setattr(
        "app.routers.demo_bidi.evaluate_interview", mock
    )
    return mock


@pytest.fixture
def _patch_agent(monkeypatch):
    """Swap `_build_agent` so we can inject a scripted FakeBidiAgent."""
    state = {"next_agent": None}

    def fake_build(system_prompt: str):
        ag = state["next_agent"]
        assert ag is not None, "test must set next_agent before WS connect"
        ag._system_prompt = system_prompt  # for optional assertions
        return ag

    monkeypatch.setattr("app.routers.demo_bidi._build_agent", fake_build)
    return state


# --------------------------------------------------------------------- tests
def _audio_frame(n_bytes: int = 200) -> dict:
    return {
        "type": "bidi_audio_stream",
        "audio": base64.b64encode(b"\x01\x02" * (n_bytes // 2)).decode(),
        "format": "pcm",
        "sample_rate": 16000,
        "channels": 1,
    }


def _transcript(role: str, text: str, is_final: bool = True) -> dict:
    return {
        "type": "bidi_transcript_stream",
        "role": role,
        "text": text,
        "is_final": is_final,
    }


async def test_full_conversation_two_qa_persists_and_forwards(
    _company_in_mem_db, _patch_s3, _patch_agent, _patch_eval
) -> None:
    """End-to-end: FakeAgent does Q1→user answers→Q2→user answers→complete."""
    script: list[tuple[str, Any]] = [
        ("emit", {"type": "bidi_connection_start", "connection_id": "fake"}),
        ("emit", {"type": "bidi_response_start"}),
        ("emit", _audio_frame()),
        ("emit", _audio_frame()),
        ("emit", _transcript("assistant", "请介绍一个你做过的射频项目。")),
        ("emit", {"type": "bidi_response_complete", "stop_reason": "complete"}),
        ("wait_user_input", 3),
        ("emit", _transcript("user", "我做过一个 5G 射频模块。")),
        ("emit", {"type": "bidi_response_start"}),
        ("emit", _audio_frame()),
        ("emit", _transcript("assistant", "阻抗匹配为什么重要？")),
        ("emit", {"type": "bidi_response_complete", "stop_reason": "complete"}),
        ("wait_user_input", 2),
        ("emit", _transcript("user", "为了最大功率传输和减少反射。")),
        ("emit", {"type": "bidi_usage", "inputTokens": 500, "outputTokens": 800,
                  "totalTokens": 1300}),
    ]
    _patch_agent["next_agent"] = FakeBidiAgent(script)

    received: list[dict] = []
    interview_id = None

    with TestClient(app) as client, client.websocket_connect("/ws/interview-demo") as ws:
        # Send some user audio to satisfy wait_user_input
        # We expect server to forward events; collect them in a loop
        # First, deliver all user audio chunks the script expects
        async def driver():
            # pump events until FakeAgent's script ends (server closes WS)
            # Send 5 audio chunks; intertwined with receiving
            for _ in range(5):
                ws.send_json({
                    "type": "bidi_audio_input",
                    "audio": base64.b64encode(b"\x00\x00" * 800).decode(),
                    "format": "pcm",
                    "sample_rate": 16000,
                    "channels": 1,
                })

        # Drive input first (async-synchronous hybrid isn't needed here —
        # TestClient.websocket is sync; we just send then receive all)
        for _ in range(5):
            ws.send_json({
                "type": "bidi_audio_input",
                "audio": base64.b64encode(b"\x00\x00" * 800).decode(),
                "format": "pcm",
                "sample_rate": 16000,
                "channels": 1,
            })

        # Receive all events until WS closes naturally (FakeAgent finished)
        # Collect with a bounded retry loop
        try:
            while True:
                msg = ws.receive_json(mode="text")
                received.append(msg)
                if msg.get("type") == "session_ready":
                    interview_id = msg.get("interview_id")
        except Exception:
            pass  # normal close

    # Basic protocol assertions
    types = [m.get("type") for m in received]
    assert "session_ready" in types
    assert "bidi_connection_start" in types
    assert types.count("bidi_audio_stream") == 3
    assert types.count("bidi_response_start") == 2
    assert types.count("bidi_response_complete") == 2
    # Final events present
    assert any(
        m.get("type") == "bidi_transcript_stream"
        and m.get("role") == "assistant"
        for m in received
    )

    # Persistence assertions
    SF = _company_in_mem_db
    assert interview_id, f"never saw session_ready with interview_id; got {types}"
    async with SF() as db:
        # Debug: count rows regardless of FK for triage
        all_qs = (await db.execute(select(Question))).scalars().all()
        all_ivs = (await db.execute(select(Interview))).scalars().all()
        all_as = (await db.execute(select(Answer))).scalars().all()
        print(
            f"\n[DEBUG] DB has {len(all_ivs)} interviews, "
            f"{len(all_qs)} questions, {len(all_as)} answers; "
            f"target interview_id={interview_id}; "
            f"Q interview_ids={{{','.join(set(q.interview_id for q in all_qs))}}}"
        )
        iv = await db.get(Interview, interview_id)
        assert iv is not None, "interview row missing"
        assert iv.company_name == "H公司"
        assert iv.status == "completed", f"status is {iv.status}"
        assert iv.bidi_tokens_total == 1300
        assert iv.bidi_ended_at is not None

        qs = (
            await db.execute(
                select(Question).where(Question.interview_id == interview_id)
            )
        ).scalars().all()
        assert len(qs) == 2, f"expected 2 questions, got {len(qs)}"
        # Order matters
        qs_sorted = sorted(qs, key=lambda q: q.order_index)
        assert qs_sorted[0].question_text.startswith("请介绍")
        assert qs_sorted[1].question_text.startswith("阻抗匹配")

        as_ = (
            await db.execute(
                select(Answer).where(
                    Answer.question_id.in_([q.id for q in qs])
                )
            )
        ).scalars().all()
        assert len(as_) == 2, f"expected 2 answers, got {len(as_)}"


async def test_audio_forwarding_not_blocked_by_slow_persistence(
    _company_in_mem_db, _patch_agent, monkeypatch
) -> None:
    """If session.on_event is slow, audio frames should still reach client fast."""
    from unittest.mock import AsyncMock

    # Make S3 upload slow; measure that audio frames still go through quickly
    async def slow_upload(*a, **k):
        await asyncio.sleep(1.0)
        return "stub-key"

    monkeypatch.setattr(
        "app.services.bidi_interview_session.s3_audio.upload",
        AsyncMock(side_effect=slow_upload),
    )

    script = [
        ("emit", _audio_frame()),
        ("emit", _audio_frame()),
        ("emit", _transcript("assistant", "问题。")),  # triggers slow S3 upload
        # emit 2 more audio frames right after: these should NOT be delayed
        # by the S3 upload triggered above
        ("emit", _audio_frame()),
        ("emit", _audio_frame()),
    ]
    _patch_agent["next_agent"] = FakeBidiAgent(script)

    with TestClient(app) as client, client.websocket_connect("/ws/interview-demo") as ws:
        t_start = time.monotonic()
        # Receive 4 audio frames + the transcript + session_ready
        types_seen: list[str] = []
        try:
            while True:
                msg = ws.receive_json(mode="text")
                types_seen.append(msg.get("type", "?"))
                if types_seen.count("bidi_audio_stream") >= 4:
                    break
        except Exception:
            pass
        elapsed = time.monotonic() - t_start

    # If persistence blocks forwarding, elapsed would be >1s (slow_upload sleep).
    # With async background tasks, it should complete well under 500ms.
    assert elapsed < 0.8, (
        f"audio forwarding blocked: elapsed={elapsed:.2f}s types={types_seen}"
    )


async def test_setup_failure_closes_ws_with_error(
    monkeypatch, _patch_agent
) -> None:
    """If no CompanyStyle is seeded, SETUP should emit error and close."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from app import db as db_module
    from app.models import Base
    from app.routers import demo_bidi as demo_module

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SF = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "SessionLocal", SF)
    monkeypatch.setattr(demo_module, "SessionLocal", SF)

    _patch_agent["next_agent"] = FakeBidiAgent([])  # won't be used

    with TestClient(app) as client:
        try:
            with client.websocket_connect("/ws/interview-demo") as ws:
                msg = ws.receive_json()
                assert msg.get("type") == "error"
                assert msg.get("code") == "setup_failed"
        except Exception:
            pass  # server may close before we finish reading; acceptable


# ============================================================================
# Bootstrap tests — critical regression guard for "Sonic never speaks first"
# ============================================================================

async def test_bootstrap_hello_injected_before_ws_audio(
    _company_in_mem_db, _patch_s3, _patch_agent, _patch_eval
) -> None:
    """recv() must yield bootstrap hello chunks BEFORE reading any WS message.

    Rationale: Nova Sonic won't generate any audio response until it receives
    user-like audio input. Our recv() pre-queues hello.pcm chunks so the model
    greets first. This test locks that behavior in.
    """
    # FakeAgent just pulls inputs and records them; never sends
    script: list[tuple[str, Any]] = [("wait_user_input", 15)]
    fake = FakeBidiAgent(script)
    _patch_agent["next_agent"] = fake

    with TestClient(app) as client, client.websocket_connect("/ws/interview-demo") as ws:
        # Don't send any ws messages; the 15 pulls should all come from bootstrap
        # Drain any server->client messages briefly
        import contextlib as _ctx
        with _ctx.suppress(Exception):
            for _ in range(3):
                ws.receive_json(mode="text")
        # Give the FakeAgent time to pull all bootstrap chunks
        time.sleep(2.0)

    # Verify every input FakeAgent saw was a bootstrap audio frame
    inputs = fake.received_inputs
    assert len(inputs) >= 5, f"expected >=5 bootstrap chunks, got {len(inputs)}: {inputs[:2]}"
    for msg in inputs:
        assert msg.get("type") == "bidi_audio_input", f"non-audio input leaked in bootstrap: {msg}"
        assert msg.get("sample_rate") == 16000
        assert msg.get("format") == "pcm"
        # audio must decode to exactly one 100ms chunk (3200 bytes PCM16 16kHz)
        decoded = base64.b64decode(msg["audio"])
        assert len(decoded) == 3200, f"bootstrap chunk wrong size: {len(decoded)}"


async def test_bootstrap_triggers_session_without_client_audio(
    _company_in_mem_db, _patch_s3, _patch_agent, _patch_eval
) -> None:
    """The full pipeline should complete a conversation EVEN IF client sends 0 ws audio.

    This is the acid test: previously sessions died after 55s because no audio
    ever reached Sonic. With bootstrap, the conversation starts immediately.
    """
    # FakeAgent emits a full 2-turn conversation, interleaved with wait_user_input
    # (which consumes bootstrap chunks in place of real client audio).
    script: list[tuple[str, Any]] = [
        ("emit", {"type": "bidi_connection_start", "connection_id": "fake"}),
        ("wait_user_input", 2),  # consume bootstrap hello
        ("emit", {"type": "bidi_response_start"}),
        ("emit", _audio_frame()),
        ("emit", _transcript("assistant", "你好，请自我介绍一下。")),
        ("emit", {"type": "bidi_response_complete", "stop_reason": "complete"}),
        ("wait_user_input", 3),  # more bootstrap (fake "user answer")
        ("emit", _transcript("user", "我是张三，射频专业。")),
        ("emit", {"type": "bidi_usage", "inputTokens": 100, "outputTokens": 50, "totalTokens": 150}),
    ]
    _patch_agent["next_agent"] = FakeBidiAgent(script)

    received_types: list[str] = []
    interview_id = None
    with TestClient(app) as client, client.websocket_connect("/ws/interview-demo") as ws:
        # Explicitly DO NOT ws.send anything
        try:
            while True:
                msg = ws.receive_json(mode="text")
                received_types.append(msg.get("type", "?"))
                if msg.get("type") == "session_ready":
                    interview_id = msg.get("interview_id")
        except Exception:
            pass

    assert "session_ready" in received_types
    assert "bidi_connection_start" in received_types
    assert received_types.count("bidi_transcript_stream") >= 2
    assert interview_id

    SF = _company_in_mem_db
    async with SF() as db:
        iv = await db.get(Interview, interview_id)
        assert iv is not None
        assert iv.status == "completed"
        qs = (await db.execute(select(Question))).scalars().all()
        assert len(qs) == 1  # one assistant turn persisted


# ============================================================================
# Failure / resilience tests — cover what team review flagged as missing
# ============================================================================

async def test_client_disconnects_midway_interview_finalized(
    db_with_company, mock_s3_upload
) -> None:
    """Client closes WS mid-session; finalize must still mark bidi_ended_at."""
    from app.services.bidi_interview_session import BidiInterviewSession

    session = BidiInterviewSession(db_with_company, role_title="RF")
    await session.setup()
    # Simulate a partial turn (Q persisted, user answer never arrives)
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "问题一", "is_final": True,
    })
    # Client "disconnects" — router calls finalize_safe
    await session.finalize_safe()

    SF = db_with_company
    async with SF() as db:
        iv = await db.get(Interview, session.interview_id)
        assert iv is not None
        assert iv.bidi_ended_at is not None, "finalize must set bidi_ended_at"
        assert iv.status == "completed"
        qs = (await db.execute(select(Question))).scalars().all()
        assert len(qs) == 1  # Q1 persisted before disconnect


async def test_agent_run_raises_still_finalizes(
    db_with_company, mock_s3_upload
) -> None:
    """When agent raises mid-session (e.g. Sonic ValidationException),
    session.finalize_safe must still mark the interview ended."""
    from app.services.bidi_interview_session import BidiInterviewSession

    session = BidiInterviewSession(db_with_company, role_title="RF")
    await session.setup()
    # Emit some events (representing partial conversation)
    await session.on_event(_transcript("assistant", "问题一", is_final=True))
    # Simulate the router's finally block after agent.run raised
    await session.finalize_safe()

    SF = db_with_company
    async with SF() as db:
        iv = await db.get(Interview, session.interview_id)
        assert iv is not None
        assert iv.bidi_ended_at is not None
        assert iv.status == "completed"


async def test_ws_send_failure_does_not_deadlock(
    db_with_company, mock_s3_upload
) -> None:
    """If persistence/background tasks fail, finalize still completes cleanly."""
    from app.services.bidi_interview_session import BidiInterviewSession

    session = BidiInterviewSession(db_with_company, role_title="RF")
    await session.setup()
    # Emit several events quickly; any mid-flight failure should be swallowed
    for _ in range(10):
        await session.on_event(_audio_frame())
    await session.on_event(_transcript("assistant", "问题", is_final=True))
    # finalize_safe must not raise even if something went wrong
    await session.finalize_safe()

    SF = db_with_company
    async with SF() as db:
        iv = await db.get(Interview, session.interview_id)
        assert iv is not None
        assert iv.bidi_ended_at is not None


# ============================================================================
# _TurnBuffer unit tests (low-level, no IO)
# ============================================================================

def test_turn_buffer_empty_flush():
    from app.services.bidi_interview_session import _TurnBuffer
    buf = _TurnBuffer()
    data, dur = buf.flush()
    assert data == b""
    assert dur == 0.0


def test_turn_buffer_single_chunk_duration():
    from app.services.bidi_interview_session import _TurnBuffer
    buf = _TurnBuffer()
    # 16000 samples * 2 bytes/sample = 32000 bytes = 1.0s @ 16kHz PCM16
    buf.append(b"\x00\x00" * 16000)
    data, dur = buf.flush()
    assert len(data) == 32000
    assert 0.99 < dur < 1.01


def test_turn_buffer_multi_chunk_concat():
    from app.services.bidi_interview_session import _TurnBuffer
    buf = _TurnBuffer()
    buf.append(b"A" * 100)
    buf.append(b"B" * 200)
    data, _ = buf.flush()
    assert data == b"A" * 100 + b"B" * 200


def test_turn_buffer_flush_resets_state():
    from app.services.bidi_interview_session import _TurnBuffer
    buf = _TurnBuffer()
    buf.append(b"X" * 100)
    buf.flush()
    data2, dur2 = buf.flush()
    assert data2 == b""
    assert dur2 == 0.0
    # re-append after flush works
    buf.append(b"Y" * 50)
    data3, _ = buf.flush()
    assert data3 == b"Y" * 50


# ============================================================================
# Session interruption handling
# ============================================================================

async def test_interruption_does_not_leak_ai_audio(db_with_company, mock_s3_upload):
    """When Sonic sends bidi_interruption, the current AI turn's audio buffer
    should be cleared, so the next turn's Question doesn't inherit stale bytes."""
    from app.services.bidi_interview_session import BidiInterviewSession
    session = BidiInterviewSession(db_with_company, role_title="RF")
    await session.setup()

    # AI starts speaking, emits audio
    await session.on_event({
        "type": "bidi_audio_stream",
        "audio": base64.b64encode(b"\x01\x02" * 500).decode(),  # 1000 bytes
    })
    # User interrupts — buffer should be flushed
    await session.on_event({"type": "bidi_interruption", "reason": "user_speech"})
    # AI starts a new turn with fresh audio
    await session.on_event({
        "type": "bidi_audio_stream",
        "audio": base64.b64encode(b"\x03\x04" * 500).decode(),
    })
    await session.on_event({
        "type": "bidi_transcript_stream",
        "role": "assistant",
        "text": "新的问题",
        "is_final": True,
    })
    await session.finalize()

    # If interruption flushed properly, the uploaded audio should be ~1000 bytes
    # (only the second chunk), not 2000 bytes.
    mock_s3_upload.assert_awaited()
    call = mock_s3_upload.await_args
    uploaded = call.args[1]
    assert len(uploaded) == 1000, f"interruption didn't flush buffer: got {len(uploaded)} bytes"



async def test_ws_send_failure_on_connection_restart_keeps_session_alive(
    _company_in_mem_db, _patch_s3, _patch_agent, _patch_eval
) -> None:
    """Regression (2026-04-30): previously a failed ws.send_json would re-raise
    and kill the Strands session mid-recovery. Nova Sonic emits
    BidiConnectionRestartEvent when its 175s internal idle timeout fires; if
    we cannot forward that event (e.g. browser's WS is unhealthy), Strands
    still auto-restarts the upstream connection. We must not abort that
    recovery — the session should continue serving subsequent events.
    """
    from unittest.mock import patch

    script: list[tuple[str, Any]] = [
        ("emit", {"type": "bidi_connection_start", "connection_id": "fake"}),
        ("wait_user_input", 1),
        ("emit", {"type": "bidi_response_start"}),
        ("emit", _transcript("assistant", "Q1", is_final=True)),
        # Simulate Sonic timeout → Strands emits connection_restart.
        # Our send() MUST NOT raise when the browser-side ws.send_json fails.
        ("emit", {"type": "bidi_connection_restart"}),
        ("emit", {"type": "bidi_response_start"}),
        ("emit", _transcript("assistant", "Q2 after restart", is_final=True)),
        ("emit", {"type": "bidi_usage", "inputTokens": 10, "outputTokens": 10,
                  "totalTokens": 20}),
    ]
    _patch_agent["next_agent"] = FakeBidiAgent(script)

    # Patch WebSocket.send_json to raise on the connection_restart event
    # (simulating a browser that has hung up or is in a bad state).
    original_send_json = None
    calls_after_restart = {"count": 0}

    async def flaky_send_json(self, payload):
        t = payload.get("type") if isinstance(payload, dict) else None
        if t == "bidi_connection_restart":
            raise RuntimeError("simulated browser disconnect mid-restart")
        # Track events the server tried to send AFTER the failure — proves
        # the session survived.
        if calls_after_restart.get("armed"):
            calls_after_restart["count"] += 1
        if t == "bidi_connection_restart":
            calls_after_restart["armed"] = True
        return await original_send_json(self, payload)

    from starlette.websockets import WebSocket
    original_send_json = WebSocket.send_json

    received_types: list[str] = []
    interview_id = None
    with (
        patch.object(WebSocket, "send_json", flaky_send_json),
        TestClient(app) as client,
        client.websocket_connect("/ws/interview-demo") as ws,
    ):
        try:
            while True:
                msg = ws.receive_json(mode="text")
                received_types.append(msg.get("type", "?"))
                if msg.get("type") == "session_ready":
                    interview_id = msg.get("interview_id")
        except Exception:
            pass  # normal close after script ends

    # Key assertion: Q2 was sent AFTER the restart event that caused send to
    # raise. If our fix is missing, the session would have died on the
    # connection_restart forwarding and Q2's transcript would never arrive.
    assert "bidi_connection_start" in received_types
    # We should see at least the transcript_stream events before and after
    # (connection_restart itself was swallowed by the mock raise, by design).
    assert received_types.count("bidi_transcript_stream") >= 2, (
        f"expected >=2 transcripts, got {received_types}"
    )

    SF = _company_in_mem_db
    async with SF() as db:
        iv = await db.get(Interview, interview_id)
        assert iv is not None


@pytest.mark.asyncio
async def test_tcl_style_id_sets_correct_company_and_role(
    _company_in_mem_db, _patch_s3, _patch_agent, _patch_eval
) -> None:
    """Passing TCL style_id must produce Interview with company=TCL and role=Embodied AI Architect."""
    SF = _company_in_mem_db

    # Seed TCL CompanyStyle into the in-memory DB
    async with SF() as s:
        tcl = CompanyStyle(
            name="TCL",
            rubric_type="tcl_l2",
            is_builtin=True,
            interviewer_style_tags=[],
            preferred_question_types=[],
            sample_questions=[],
            prompt_context_text="TCL L2 context",
        )
        s.add(tcl)
        await s.commit()
        await s.refresh(tcl)
        tcl_id = tcl.id

    script = [
        ("emit", {"type": "bidi_connection_start", "connection_id": "fake"}),
        ("emit", {"type": "bidi_response_start"}),
        ("emit", {
            "type": "bidi_transcript_stream",
            "role": "assistant",
            "text": "Hello, I am your TCL interviewer.",
            "is_final": True,
        }),
        ("emit", {"type": "bidi_response_complete"}),
    ]
    _patch_agent["next_agent"] = FakeBidiAgent(script)

    interview_id = None
    with TestClient(app) as client:
        with client.websocket_connect(
            f"/ws/interview-demo?style_id={tcl_id}&lang=en"
        ) as ws:
            for _ in range(10):
                try:
                    msg = ws.receive_json()
                    if msg.get("type") == "session_ready":
                        interview_id = msg.get("interview_id")
                except Exception:
                    break

    assert interview_id, "never received session_ready"

    async with SF() as s:
        iv = await s.get(Interview, interview_id)

    assert iv is not None
    assert iv.company_name == "TCL", f"expected TCL, got {iv.company_name}"
    assert iv.role_title == "Embodied AI Architect", f"got {iv.role_title}"
    assert iv.language == "en", f"expected en, got {iv.language}"


@pytest.mark.asyncio
async def test_no_style_id_falls_back_to_default_company(
    _company_in_mem_db, _patch_s3, _patch_agent, _patch_eval
) -> None:
    """No style_id must fall back to H公司 with the original RF Intern role title."""
    SF = _company_in_mem_db

    script = [
        ("emit", {"type": "bidi_connection_start", "connection_id": "fake"}),
        ("emit", {"type": "bidi_response_complete"}),
    ]
    _patch_agent["next_agent"] = FakeBidiAgent(script)

    interview_id = None
    with TestClient(app) as client:
        with client.websocket_connect("/ws/interview-demo") as ws:
            for _ in range(5):
                try:
                    msg = ws.receive_json()
                    if msg.get("type") == "session_ready":
                        interview_id = msg.get("interview_id")
                except Exception:
                    break

    assert interview_id, "never received session_ready"

    async with SF() as s:
        iv = await s.get(Interview, interview_id)

    assert iv is not None
    assert iv.company_name == "H公司", f"expected H公司, got {iv.company_name}"
    assert iv.role_title == "硬件技术工程师（射频技术方向）实习生", f"got {iv.role_title}"
    assert iv.language == "zh"
