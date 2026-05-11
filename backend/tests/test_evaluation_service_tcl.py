"""Tests for TCL evaluation pipeline dispatch."""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import CompanyStyle, Evaluation, Interview
from app.services.bidi_interview_session import BidiInterviewSession
from app.services.evaluation_service import evaluate_interview


@pytest_asyncio.fixture
async def db_with_tcl(session_factory):
    async with session_factory() as s:
        cs = CompanyStyle(
            name="TCL",
            rubric_type="tcl_l2",
            interviewer_style_tags=["技术深度"],
            preferred_question_types=["架构设计"],
            sample_questions=["描述你的架构设计经验"],
            prompt_context_text="TCL L2 评估...",
            is_builtin=True,
        )
        s.add(cs)
        await s.commit()
    return session_factory


@pytest.mark.asyncio
async def test_tcl_pipeline_writes_dimension_scores(db_with_tcl, mock_s3_upload):
    """TCL pipeline: dimension_scores populated correctly."""
    async with db_with_tcl() as s:
        cs = (await s.execute(
            select(CompanyStyle).where(CompanyStyle.name == "TCL")
        )).scalar_one()
        tcl_id = cs.id

    session = BidiInterviewSession(
        db_with_tcl,
        role_title="Embodied AI Architect",
        company_style_id=tcl_id,
    )
    await session.setup()
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "请描述你设计过的具身AI系统架构。", "is_final": True,
    })
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "user",
        "text": "我设计了一个基于ROS2的家庭机器人系统，包括感知模块、规划模块和执行模块。", "is_final": True,
    })
    await session.finalize(status="completed")

    tcl_stage1 = {
        "content_checkpoints": {
            "tech_depth_knowledge": {"result": "Pass", "reason": "了解ROS2"},
            "tech_depth_impl":      {"result": "Pass", "reason": "有实现经验"},
            "arch_e2e_design":      {"result": "Pass", "reason": "描述了端到端架构"},
            "arch_integration":     {"result": "No-Pass", "reason": "未提到硬件集成"},
            "tcl_competency_star":  {"result": "Pass", "reason": "有清晰陈述"},
            "tcl_culture_fit":      {"result": "No-Pass", "reason": "未提文化契合"},
        },
        "expression_score": 72,
        "improvement_suggestions": ["加入硬件集成细节"],
        "ideal_answer": "参考答案...",
    }
    tcl_stage2 = {
        "overall_content_score": 70, "overall_expression_score": 65,
        "overall_voice_score": 0, "overall_score": 60, "overall_result": "Borderline",
        "overall_summary": "技术深度良好但集成经验不足",
        "strengths": ["ROS2架构设计"],
        "top_3_improvement_priorities": ["硬件集成", "文化契合表达", "STAR结构"],
    }
    dummy_voice = {
        "duration_total_sec": 10, "duration_speaking_sec": 8, "speaking_ratio": 0.8,
        "talk_speed_cps": 4.0, "pause_count": 2, "pause_count_per_minute": 12,
        "longest_pause_sec": 0.5, "filler_word_count": 0, "filler_word_ratio": 0.0,
        "filler_words_detected": [], "first_response_delay_sec": 1.0,
        "hesitation_count": 0, "volume_mean": 0.5, "volume_stability": 0.2,
        "accurate_wpm": 0, "accurate_speaking_sec": 0, "low_confidence_ratio": 0.0,
        "low_confidence_words": [], "sentiment_overall": "POSITIVE",
        "sentiment_scores": {"positive": 0.9, "negative": 0.1, "neutral": 0.0, "mixed": 0.0},
        "transcribe_sentiment": {"overall": "POSITIVE"},
        "talk_speed_wps": 0,
    }

    with patch(
        "app.services.evaluation_service.bedrock_claude.invoke_json",
        side_effect=[
            (tcl_stage1, {"cost_usd": 0.01}),
            (tcl_stage2, {"cost_usd": 0.01}),
        ],
    ), patch(
        "app.services.evaluation_service._compute_voice_features",
        new=AsyncMock(return_value=dummy_voice),
    ):
        await evaluate_interview(db_with_tcl, session.interview_id)

    async with db_with_tcl() as s:
        evals = (await s.execute(
            select(Evaluation).where(Evaluation.interview_id == session.interview_id)
        )).scalars().all()

    per_q = [e for e in evals if e.question_id is not None]
    assert len(per_q) == 1
    ev = per_q[0]
    assert ev.dimension_scores != {}
    assert "tech_depth" in ev.dimension_scores
    assert "architecture" in ev.dimension_scores
    assert "competency" in ev.dimension_scores
    assert "culture" in ev.dimension_scores
    assert ev.dimension_scores["tech_depth"] == 100
    assert ev.dimension_scores["architecture"] == 50


@pytest.mark.asyncio
async def test_faang_pipeline_dimension_scores_empty(db_with_company, mock_s3_upload):
    """某公司 pipeline: dimension_scores must be empty dict."""
    session = BidiInterviewSession(db_with_company, role_title="RF")
    await session.setup()
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "请介绍你的射频项目。", "is_final": True,
    })
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "user",
        "text": "我设计了5G天线，使用HFSS仿真验证。", "is_final": True,
    })
    await session.finalize(status="completed")

    faang_stage1 = {
        "content_checkpoints": {
            "star_structure": {"result": "Pass", "reason": "ok"},
            "specificity_details": {"result": "Pass", "reason": "ok"},
            "impact_results": {"result": "No-Pass", "reason": "no"},
            "leadership_ownership": {"result": "No-Pass", "reason": "no"},
            "problem_solving": {"result": "Pass", "reason": "ok"},
            "communication_clarity": {"result": "Pass", "reason": "ok"},
        },
        "expression_score": 70,
        "improvement_suggestions": ["加入数据"],
        "ideal_answer": "参考...",
    }
    faang_stage2 = {
        "overall_content_score": 67, "overall_expression_score": 70,
        "overall_voice_score": 0, "overall_score": 55, "overall_result": "Borderline",
        "overall_summary": "中等", "strengths": ["基础扎实"],
        "top_3_improvement_priorities": ["数据", "结构", "犹豫"],
    }
    dummy_voice = {
        "duration_total_sec": 10, "duration_speaking_sec": 8, "speaking_ratio": 0.8,
        "talk_speed_cps": 4.0, "pause_count": 2, "pause_count_per_minute": 12,
        "longest_pause_sec": 0.5, "filler_word_count": 0, "filler_word_ratio": 0.0,
        "filler_words_detected": [], "first_response_delay_sec": 1.0,
        "hesitation_count": 0, "volume_mean": 0.5, "volume_stability": 0.2,
        "accurate_wpm": 0, "accurate_speaking_sec": 0, "low_confidence_ratio": 0.0,
        "low_confidence_words": [], "sentiment_overall": "NEUTRAL",
        "sentiment_scores": {"positive": 0.5, "negative": 0.1, "neutral": 0.4, "mixed": 0.0},
        "transcribe_sentiment": {"overall": "NEUTRAL"},
        "talk_speed_wps": 0,
    }

    with patch(
        "app.services.evaluation_service.bedrock_claude.invoke_json",
        side_effect=[
            (faang_stage1, {"cost_usd": 0.01}),
            (faang_stage2, {"cost_usd": 0.01}),
        ],
    ), patch(
        "app.services.evaluation_service._compute_voice_features",
        new=AsyncMock(return_value=dummy_voice),
    ):
        await evaluate_interview(db_with_company, session.interview_id)

    async with db_with_company() as s:
        evals = (await s.execute(
            select(Evaluation).where(Evaluation.interview_id == session.interview_id)
        )).scalars().all()

    per_q = [e for e in evals if e.question_id is not None]
    assert len(per_q) == 1
    assert per_q[0].dimension_scores == {}
