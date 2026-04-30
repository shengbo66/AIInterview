"""Tests for BidiInterviewSession — setup, event handling, finalize."""
import base64
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models import Answer, CompanyStyle, Interview, Question
from app.services.bidi_interview_session import (
    BidiInterviewSession,
    compose_system_prompt,
)

# ---------------------------------------------------------------- fixtures


# ---------------------------------------------------------- unit: compose


def test_compose_system_prompt_uses_style_text():
    cs = CompanyStyle(
        name="华为",
        prompt_context_text="四大维度：A、B、C、D。",
        sample_questions=["Q1", "Q2", "Q3"],
    )
    prompt = compose_system_prompt(cs, role_title="射频实习生")
    assert "华为" in prompt
    assert "射频实习生" in prompt
    assert "四大维度：A、B、C、D。" in prompt
    assert "Q1" in prompt and "Q2" in prompt
    assert "开场" in prompt  # rule line


def test_compose_handles_missing_optional_fields():
    cs = CompanyStyle(name="Acme", prompt_context_text="", sample_questions=None)
    prompt = compose_system_prompt(cs, role_title="Eng")
    assert "Acme" in prompt
    assert "Eng" in prompt


# ------------------------------------------------------- setup & lifecycle


async def test_setup_creates_interview_row(db_with_huawei):
    session = BidiInterviewSession(db_with_huawei, role_title="RF Intern")
    await session.setup()

    assert session.interview_id is not None
    assert "华为" in session.system_prompt
    assert "RF Intern" in session.system_prompt

    async with db_with_huawei() as db:
        iv = await db.get(Interview, session.interview_id)
        assert iv is not None
        assert iv.company_name == "华为"
        assert iv.role_title == "RF Intern"
        assert iv.status == "in_progress"
        assert iv.bidi_started_at is not None


async def test_setup_raises_when_no_style_seeded(session_factory):
    session = BidiInterviewSession(session_factory, role_title="RF")
    with pytest.raises(RuntimeError, match="No builtin CompanyStyle"):
        await session.setup()


async def test_system_prompt_before_setup_raises(db_with_huawei):
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    with pytest.raises(RuntimeError, match="call setup"):
        _ = session.system_prompt


# ---------------------------------------------------- event: transcript


async def test_assistant_final_creates_question_and_uploads_audio(
    db_with_huawei, mock_s3_upload
):
    """Q row is committed synchronously; S3 upload + s3_key patch are
    background tasks that complete after session.finalize() drains them.
    """
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    await session.setup()

    # AI speaks: first buffer audio chunks, then a final assistant transcript
    pcm = b"\x01\x02" * 1000  # 2000 bytes
    await session.on_event({
        "type": "bidi_audio_stream",
        "audio": base64.b64encode(pcm).decode(),
    })
    await session.on_event({
        "type": "bidi_transcript_stream",
        "role": "assistant",
        "text": "请介绍你做过的一个射频项目。",
        "is_final": True,
    })
    # Q row should be present even before finalize (synchronous commit):
    async with db_with_huawei() as db:
        qs = (await db.execute(select(Question))).scalars().all()
        assert len(qs) == 1
        assert qs[0].order_index == 0
        assert qs[0].question_text.startswith("请介绍")

    # finalize() drains background tasks (S3 upload + s3_key patch)
    await session.finalize()

    mock_s3_upload.assert_awaited_once()
    s3_key = mock_s3_upload.await_args.args[0]
    assert s3_key.startswith(f"interviews/{session.interview_id}/q0.pcm")

    async with db_with_huawei() as db:
        q = (await db.execute(select(Question))).scalar_one()
        assert q.question_audio_s3_key == s3_key


async def test_partial_transcript_is_ignored(db_with_huawei, mock_s3_upload):
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    await session.setup()

    await session.on_event({
        "type": "bidi_transcript_stream",
        "role": "assistant",
        "text": "请介绍",
        "is_final": False,
    })

    async with db_with_huawei() as db:
        qs = (await db.execute(select(Question))).scalars().all()
        assert len(qs) == 0
    mock_s3_upload.assert_not_awaited()


async def test_user_final_creates_answer_linked_to_last_question(
    db_with_huawei, mock_s3_upload
):
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    await session.setup()

    # 1. AI asks Q1
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "Q1?", "is_final": True,
    })
    # 2. User answers (with some buffered PCM for duration calc)
    session.append_user_audio(b"\x00\x00" * 16000)  # 1 sec @ 16kHz PCM16
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "user",
        "text": "我做过一个5G射频模块项目...", "is_final": True,
    })

    async with db_with_huawei() as db:
        q = (await db.execute(select(Question))).scalar_one()
        a = (await db.execute(select(Answer))).scalar_one()
        assert a.question_id == q.id
        assert "5G射频模块" in a.transcript_text
        assert 0.9 < a.duration_sec < 1.1


async def test_user_turn_before_any_question_is_dropped(db_with_huawei):
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    await session.setup()

    await session.on_event({
        "type": "bidi_transcript_stream", "role": "user",
        "text": "hello?", "is_final": True,
    })
    async with db_with_huawei() as db:
        answers = (await db.execute(select(Answer))).scalars().all()
        assert answers == []


async def test_multiple_user_finals_coalesce_to_single_answer(
    db_with_huawei, mock_s3_upload
):
    """Regression: Nova Sonic can emit multiple is_final=True user transcripts
    within the same user turn (each sentence / endpointed utterance).
    They must UPDATE one Answer row, not attempt to INSERT new rows — the
    UNIQUE constraint on answer.question_id would cause IntegrityError
    and eventually crash the session.
    """
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    await session.setup()

    # AI asks Q1
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "请介绍你做过的射频项目。", "is_final": True,
    })

    # User answers in 3 endpointed fragments (common with Sonic VAD).
    # Each fragment brings ~1s of buffered PCM.
    for fragment in ["我做过5G射频模块,", "从需求分析开始,", "一直到测试验证。"]:
        session.append_user_audio(b"\x00\x00" * 16000)  # 1s PCM16 @ 16kHz
        await session.on_event({
            "type": "bidi_transcript_stream", "role": "user",
            "text": fragment, "is_final": True,
        })

    async with db_with_huawei() as db:
        answers = (await db.execute(select(Answer))).scalars().all()
        assert len(answers) == 1, "All fragments must coalesce to one Answer row"
        a = answers[0]
        # Text is concatenated in order of arrival
        assert a.transcript_text == "我做过5G射频模块,从需求分析开始,一直到测试验证。"
        # Duration is cumulative (~3s)
        assert 2.8 < a.duration_sec < 3.2


async def test_s3_upload_failure_does_not_break_persistence(
    db_with_huawei, monkeypatch
):
    fail_up = AsyncMock(side_effect=RuntimeError("S3 boom"))
    monkeypatch.setattr(
        "app.services.bidi_interview_session.s3_audio.upload", fail_up
    )
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    await session.setup()

    await session.on_event({
        "type": "bidi_audio_stream",
        "audio": base64.b64encode(b"\x01\x02" * 100).decode(),
    })
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "Q1?", "is_final": True,
    })
    # Let the background S3 upload task run to completion (it will fail)
    await session.finalize()

    async with db_with_huawei() as db:
        q = (await db.execute(select(Question))).scalar_one()
        assert q.question_text == "Q1?"
        assert q.question_audio_s3_key is None  # upload failed, key stays null


# --------------------------------------------------------- event: usage


async def test_usage_event_accumulates_to_finalize(db_with_huawei, mock_s3_upload):
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    await session.setup()

    await session.on_event({
        "type": "bidi_usage", "inputTokens": 100, "outputTokens": 200, "totalTokens": 300,
    })
    # later event supersedes (Sonic sends cumulative values)
    await session.on_event({
        "type": "bidi_usage", "inputTokens": 150, "outputTokens": 450, "totalTokens": 600,
    })
    await session.finalize()

    async with db_with_huawei() as db:
        iv = await db.get(Interview, session.interview_id)
        assert iv.bidi_tokens_total == 600
        # cost = 150/1000*0.0034 + 450/1000*0.0136 = 0.00051 + 0.00612 = 0.00663
        assert 0.0065 < iv.bidi_cost_usd < 0.0068


# ------------------------------------------------------------- finalize


async def test_finalize_marks_completed_and_sets_timestamps(
    db_with_huawei, mock_s3_upload
):
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    await session.setup()
    await session.finalize()

    async with db_with_huawei() as db:
        iv = await db.get(Interview, session.interview_id)
        assert iv.status == "completed"
        assert iv.bidi_ended_at is not None
        assert iv.ended_at is not None


async def test_finalize_is_idempotent(db_with_huawei, mock_s3_upload):
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    await session.setup()
    await session.finalize()
    # Second call should be a no-op, not raise
    await session.finalize()


async def test_finalize_safe_never_raises(db_with_huawei, mock_s3_upload, monkeypatch):
    # Force inner finalize to blow up; finalize_safe should swallow
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    await session.setup()

    async def boom(*_a, **_k):
        raise RuntimeError("inner boom")
    monkeypatch.setattr(session, "finalize", boom)
    # must not raise
    await session.finalize_safe()


async def test_events_before_setup_are_silently_ignored(session_factory):
    session = BidiInterviewSession(session_factory, role_title="RF")
    # No setup(); should not raise
    await session.on_event({"type": "bidi_usage", "totalTokens": 42})
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "x", "is_final": True,
    })
