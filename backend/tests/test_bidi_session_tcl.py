"""Tests for BidiInterviewSession with company_style_id and language params."""
import pytest
import pytest_asyncio

from app.models import CompanyStyle, Interview
from app.services.bidi_interview_session import BidiInterviewSession


@pytest_asyncio.fixture
async def db_with_both_styles(session_factory):
    async with session_factory() as s:
        s.add(CompanyStyle(
            name="某公司", rubric_type="faang", is_builtin=True,
            interviewer_style_tags=[], preferred_question_types=[],
            sample_questions=[], prompt_context_text="某公司上下文",
        ))
        s.add(CompanyStyle(
            name="TCL", rubric_type="tcl_l2", is_builtin=True,
            interviewer_style_tags=[], preferred_question_types=[],
            sample_questions=[], prompt_context_text="TCL上下文",
        ))
        await s.commit()
    return session_factory


@pytest.mark.asyncio
async def test_setup_with_style_id_loads_tcl(db_with_both_styles, mock_s3_upload):
    """Passing style_id should load the specified CompanyStyle."""
    from sqlalchemy import select
    async with db_with_both_styles() as s:
        cs = (await s.execute(
            select(CompanyStyle).where(CompanyStyle.name == "TCL")
        )).scalar_one()
        tcl_id = cs.id

    session = BidiInterviewSession(
        db_with_both_styles,
        role_title="Embodied AI Architect",
        company_style_id=tcl_id,
        language="en",
    )
    await session.setup()

    async with db_with_both_styles() as s:
        iv = await s.get(Interview, session.interview_id)
    assert iv.company_name == "TCL"
    assert iv.language == "en"


@pytest.mark.asyncio
async def test_setup_fallback_uses_first_builtin(db_with_both_styles, mock_s3_upload):
    """style_id=None uses original logic: first builtin CompanyStyle."""
    session = BidiInterviewSession(
        db_with_both_styles,
        role_title="RF Intern",
    )
    await session.setup()

    async with db_with_both_styles() as s:
        iv = await s.get(Interview, session.interview_id)
    assert iv.company_name == "某公司"
    assert iv.language == "zh"


@pytest.mark.asyncio
async def test_setup_invalid_style_id_raises(db_with_both_styles, mock_s3_upload):
    """Invalid style_id should raise RuntimeError."""
    session = BidiInterviewSession(
        db_with_both_styles,
        role_title="RF Intern",
        company_style_id="nonexistent-id",
    )
    with pytest.raises(RuntimeError, match="not found"):
        await session.setup()


@pytest.mark.asyncio
async def test_system_prompt_language_en(db_with_both_styles, mock_s3_upload):
    """language='en' should produce English system prompt."""
    from sqlalchemy import select
    async with db_with_both_styles() as s:
        cs = (await s.execute(
            select(CompanyStyle).where(CompanyStyle.name == "TCL")
        )).scalar_one()
        tcl_id = cs.id

    session = BidiInterviewSession(
        db_with_both_styles,
        role_title="Embodied AI Architect",
        company_style_id=tcl_id,
        language="en",
    )
    await session.setup()
    prompt = session.system_prompt
    assert "You are" in prompt or "interviewer" in prompt.lower()
