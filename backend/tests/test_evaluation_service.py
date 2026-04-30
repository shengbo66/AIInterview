"""Tests for evaluation_service pipeline."""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models import Evaluation, Interview
from app.services.evaluation_service import evaluate_interview


@pytest.mark.asyncio
async def test_evaluation_pipeline_success(db_with_huawei, mock_s3_upload):
    """Full pipeline: 2 Q/A pairs → per-question evals + overall eval."""
    from app.services.bidi_interview_session import BidiInterviewSession

    # Setup interview with 2 Q/A pairs
    session = BidiInterviewSession(db_with_huawei, role_title="RF")
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
        await evaluate_interview(db_with_huawei, session.interview_id)

    # Verify evaluations
    async with db_with_huawei() as db:
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
async def test_evaluation_skips_empty_interview(db_with_huawei, mock_s3_upload):
    """Interview with 0 answered questions → status = evaluation_skipped."""
    from app.services.bidi_interview_session import BidiInterviewSession

    session = BidiInterviewSession(db_with_huawei, role_title="RF")
    await session.setup()
    # Only AI question, no user answer
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "请自我介绍。", "is_final": True,
    })
    await session.finalize(status="completed")

    await evaluate_interview(db_with_huawei, session.interview_id)

    async with db_with_huawei() as db:
        iv = await db.get(Interview, session.interview_id)
        assert iv.status == "evaluation_skipped"
        evals = (await db.execute(select(Evaluation))).scalars().all()
        assert len(evals) == 0


@pytest.mark.asyncio
async def test_evaluation_failure_marks_status(db_with_huawei, mock_s3_upload):
    """Claude failure → status = evaluation_failed."""
    from app.services.bidi_interview_session import BidiInterviewSession

    session = BidiInterviewSession(db_with_huawei, role_title="RF")
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
        await evaluate_interview(db_with_huawei, session.interview_id)

    async with db_with_huawei() as db:
        iv = await db.get(Interview, session.interview_id)
        assert iv.status == "evaluation_failed"
