"""Tests for evaluation_service pipeline."""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models import Evaluation, Interview
from app.services.evaluation_service import evaluate_interview


@pytest.mark.asyncio
async def test_evaluation_pipeline_success(db_with_company, mock_s3_upload):
    """Full pipeline: 2 Q/A pairs → per-question evals + overall eval."""
    from app.services.bidi_interview_session import BidiInterviewSession

    # Setup interview with 2 Q/A pairs
    session = BidiInterviewSession(db_with_company, role_title="RF")
    await session.setup()
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "请介绍你做过的射频项目。", "is_final": True,
    })
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "user",
        "text": "我做过5G射频模块设计，使用ADS仿真。", "is_final": True,
    })
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "阻抗匹配为什么重要？", "is_final": True,
    })
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "user",
        "text": "为了最大功率传输和减少反射损耗。", "is_final": True,
    })
    await session.finalize(status="completed")

    # Mock Claude responses
    stage1_response = {
        "content_checkpoints": {
            "star_structure": {"result": "Pass", "reason": "ok"},
            "specificity_details": {"result": "Pass", "reason": "ok"},
            "impact_results": {"result": "No-Pass", "reason": "no data"},
            "leadership_ownership": {"result": "No-Pass", "reason": "no"},
            "problem_solving": {"result": "Pass", "reason": "ok"},
            "communication_clarity": {"result": "Pass", "reason": "ok"},
        },
        "expression_score": 70,
        "improvement_suggestions": ["加入具体数据", "用STAR结构"],
        "ideal_answer": "参考答案...",
    }
    stage2_response = {
        "overall_content_score": 67,
        "overall_expression_score": 70,
        "overall_voice_score": 0,
        "overall_score": 55,
        "overall_result": "Borderline",
        "overall_summary": "表现中等",
        "strengths": ["技术基础扎实"],
        "top_3_improvement_priorities": ["加入量化数据", "改善结构", "减少犹豫"],
    }
    mock_meta = {"cost_usd": 0.01, "elapsed_sec": 2.0}

    with patch("app.services.evaluation_service.bedrock_claude") as mock_claude:
        mock_claude.invoke_json = AsyncMock(
            side_effect=[
                (stage1_response, mock_meta),
                (stage1_response, mock_meta),
                (stage2_response, mock_meta),
            ]
        )
        await evaluate_interview(db_with_company, session.interview_id)

    # Verify evaluations
    async with db_with_company() as db:
        evals = (await db.execute(select(Evaluation))).scalars().all()
        assert len(evals) == 3  # 2 per-question + 1 overall

        per_q = [e for e in evals if e.question_id is not None]
        overall = [e for e in evals if e.question_id is None]
        assert len(per_q) == 2
        assert len(overall) == 1
        assert overall[0].overall_result == "Borderline"
        assert overall[0].overall_score == 55

        # Interview status updated
        iv = await db.get(Interview, session.interview_id)
        assert iv.status == "evaluated"


@pytest.mark.asyncio
async def test_evaluation_skips_empty_interview(db_with_company, mock_s3_upload):
    """Interview with 0 answered questions → status = evaluation_skipped."""
    from app.services.bidi_interview_session import BidiInterviewSession

    session = BidiInterviewSession(db_with_company, role_title="RF")
    await session.setup()
    # Only AI question, no user answer
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "请自我介绍。", "is_final": True,
    })
    await session.finalize(status="completed")

    await evaluate_interview(db_with_company, session.interview_id)

    async with db_with_company() as db:
        iv = await db.get(Interview, session.interview_id)
        assert iv.status == "evaluation_skipped"
        evals = (await db.execute(select(Evaluation))).scalars().all()
        assert len(evals) == 0


@pytest.mark.asyncio
async def test_evaluation_failure_marks_status(db_with_company, mock_s3_upload):
    """Claude failure → status = evaluation_failed."""
    from app.services.bidi_interview_session import BidiInterviewSession

    session = BidiInterviewSession(db_with_company, role_title="RF")
    await session.setup()
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "问题1", "is_final": True,
    })
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "user",
        "text": "回答1", "is_final": True,
    })
    await session.finalize(status="completed")

    with patch("app.services.evaluation_service.bedrock_claude") as mock_claude:
        mock_claude.invoke_json = AsyncMock(
            side_effect=RuntimeError("Claude API down")
        )
        await evaluate_interview(db_with_company, session.interview_id)

    async with db_with_company() as db:
        iv = await db.get(Interview, session.interview_id)
        assert iv.status == "evaluation_failed"


# ---------- _compute_voice_features unit tests (FR-4) ----------


@pytest.mark.asyncio
async def test_compute_voice_no_s3_key_returns_dummy():
    """No audio recorded → fallback to dummy, log INFO."""
    from app.models import Answer
    from app.services.evaluation_service import _DUMMY_VOICE, _compute_voice_features

    answer = Answer(
        id="a1",
        question_id="q1",
        user_audio_s3_key=None,
        transcript_text="测试",
        duration_sec=3.5,
    )
    result = await _compute_voice_features(answer, "test-iv-id")
    assert result["duration_total_sec"] == 3.5  # passthrough from answer
    assert result["talk_speed_cps"] == 0
    assert result["filler_word_count"] == 0
    # Same shape as dummy
    assert set(result.keys()) == set(_DUMMY_VOICE.keys())


@pytest.mark.asyncio
async def test_compute_voice_s3_error_returns_dummy():
    """S3 download raises → fallback to dummy, log WARNING."""
    from app.models import Answer
    from app.services.evaluation_service import _compute_voice_features

    answer = Answer(
        id="a2",
        question_id="q2",
        user_audio_s3_key="interviews/xxx/q0.pcm",
        transcript_text="测试",
        duration_sec=5.0,
    )
    with patch("app.services.evaluation_service.s3_audio") as mock_s3:
        mock_s3.download_bytes = AsyncMock(side_effect=Exception("NoSuchKey"))
        result = await _compute_voice_features(answer, "test-iv-id")
    assert result["duration_total_sec"] == 5.0
    assert result["talk_speed_cps"] == 0


@pytest.mark.asyncio
async def test_compute_voice_short_pcm_returns_dummy():
    """PCM < 1 second → analyze() raises ValueError → fallback."""
    from app.models import Answer
    from app.services.evaluation_service import _compute_voice_features

    answer = Answer(
        id="a3",
        question_id="q3",
        user_audio_s3_key="interviews/xxx/q0.pcm",
        transcript_text="嗯",
        duration_sec=0.5,
    )
    short_pcm = b"\x00\x00" * 100  # 100 samples = way below 1s threshold
    with patch("app.services.evaluation_service.s3_audio") as mock_s3, \
         patch("app.services.evaluation_service.transcribe_client") as mock_tr, \
         patch("app.services.evaluation_service.comprehend_client") as mock_cp:
        mock_s3.download_bytes = AsyncMock(return_value=short_pcm)
        mock_tr.submit_job = AsyncMock(return_value="job")
        mock_tr.wait_for_completion = AsyncMock(return_value={"status": "COMPLETED"})
        mock_tr.parse_words = AsyncMock(return_value=[])
        mock_cp.detect_sentiment = AsyncMock(
            return_value={"overall": "UNKNOWN", "scores": {"positive": 0, "negative": 0, "neutral": 0, "mixed": 0}}
        )
        result = await _compute_voice_features(answer, "test-iv-id")
    assert result["duration_total_sec"] == 0.5
    assert result["talk_speed_cps"] == 0


@pytest.mark.asyncio
async def test_compute_voice_success_returns_real_features():
    """Happy path: S3 returns valid PCM → analyze() → real features."""
    import math
    import struct

    from app.models import Answer
    from app.services.evaluation_service import _compute_voice_features

    # Generate 2s speech-like PCM (above 1s threshold)
    n = 16000 * 2
    pcm = struct.pack(
        f"<{n}h",
        *[int(6000 * math.sin(2 * math.pi * 200 * i / 16000)) for i in range(n)],
    )
    answer = Answer(
        id="a4",
        question_id="q4",
        user_audio_s3_key="interviews/xxx/q0.pcm",
        transcript_text="我对射频方向很感兴趣",  # 9 Chinese chars
        duration_sec=2.0,
    )
    with patch("app.services.evaluation_service.s3_audio") as mock_s3, \
         patch("app.services.evaluation_service.transcribe_client") as mock_tr, \
         patch("app.services.evaluation_service.comprehend_client") as mock_cp:
        mock_s3.download_bytes = AsyncMock(return_value=pcm)
        mock_tr.submit_job = AsyncMock(return_value="job")
        mock_tr.wait_for_completion = AsyncMock(return_value={"status": "COMPLETED"})
        mock_tr.parse_words = AsyncMock(return_value=[])
        mock_cp.detect_sentiment = AsyncMock(
            return_value={
                "overall": "NEUTRAL",
                "scores": {"positive": 0.1, "negative": 0.1, "neutral": 0.7, "mixed": 0.1},
            }
        )
        result = await _compute_voice_features(answer, "test-iv-id")

    assert result["duration_total_sec"] == pytest.approx(2.0, abs=0.1)
    assert result["talk_speed_cps"] > 0  # 9 chars / ~2s = ~4.5
    assert "filler_words_detected" in result
    assert "speaking_ratio" in result
