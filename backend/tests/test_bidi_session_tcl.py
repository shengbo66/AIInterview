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


@pytest.mark.asyncio
async def test_system_prompt_zh_contains_chinese_rules(db_with_both_styles, mock_s3_upload):
    """language='zh' system prompt must contain Chinese interview rules and role title."""
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
        language="zh",
    )
    await session.setup()
    prompt = session.system_prompt
    assert "TCL 面试官" in prompt
    assert "Embodied AI Architect" in prompt
    assert "每次只问一个问题" in prompt
    assert "You are" not in prompt  # must not mix in English template


@pytest.mark.asyncio
async def test_system_prompt_en_contains_english_rules(db_with_both_styles, mock_s3_upload):
    """language='en' system prompt must contain English interview rules."""
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
    assert "You are" in prompt
    assert "Embodied AI Architect" in prompt
    assert "Ask one question at a time" in prompt
    assert "每次只问一个问题" not in prompt  # must not mix in Chinese template


@pytest.mark.asyncio
async def test_company_style_zh_prompt_unchanged(db_with_both_styles, mock_s3_upload):
    """某公司 zh prompt must use original Chinese template (regression guard)."""
    session = BidiInterviewSession(
        db_with_both_styles,
        role_title="硬件技术工程师",
        # no company_style_id — fallback to 某公司
    )
    await session.setup()
    prompt = session.system_prompt
    assert "某公司 面试官" in prompt
    assert "硬件技术工程师" in prompt
    assert "每次只问一个问题" in prompt
