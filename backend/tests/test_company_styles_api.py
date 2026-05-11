"""Tests for GET /api/company-styles?builtin=true."""
import pytest
from httpx import AsyncClient

from app.models import CompanyStyle


@pytest.mark.asyncio
async def test_list_builtin_only(client: AsyncClient, session_factory):
    """Test ?builtin=true filters to only built-in styles."""
    # Seed both builtin and custom styles
    async with session_factory() as s:
        s.add(CompanyStyle(
            name="某公司", rubric_type="faang", is_builtin=True,
            interviewer_style_tags=[], preferred_question_types=[],
            sample_questions=[], prompt_context_text="ctx",
        ))
        s.add(CompanyStyle(
            name="TCL", rubric_type="tcl_l2", is_builtin=True,
            interviewer_style_tags=[], preferred_question_types=[],
            sample_questions=[], prompt_context_text="ctx",
        ))
        s.add(CompanyStyle(
            name="自定义公司", rubric_type="faang", is_builtin=False,
            interviewer_style_tags=[], preferred_question_types=[],
            sample_questions=[], prompt_context_text="ctx",
        ))
        await s.commit()

    resp = await client.get("/api/company-styles?builtin=true")
    assert resp.status_code == 200
    data = resp.json()
    assert all(s["is_builtin"] for s in data), "All returned styles should be builtin"
    names = [s["name"] for s in data]
    assert "某公司" in names
    assert "TCL" in names
    assert "自定义公司" not in names


@pytest.mark.asyncio
async def test_list_all_without_filter(client: AsyncClient, session_factory):
    """Test that default (no filter) returns all styles."""
    # Seed both builtin and custom styles
    async with session_factory() as s:
        s.add(CompanyStyle(
            name="某公司", rubric_type="faang", is_builtin=True,
            interviewer_style_tags=[], preferred_question_types=[],
            sample_questions=[], prompt_context_text="ctx",
        ))
        s.add(CompanyStyle(
            name="自定义公司", rubric_type="faang", is_builtin=False,
            interviewer_style_tags=[], preferred_question_types=[],
            sample_questions=[], prompt_context_text="ctx",
        ))
        await s.commit()

    resp = await client.get("/api/company-styles")
    assert resp.status_code == 200
    data = resp.json()
    names = [s["name"] for s in data]
    assert "某公司" in names
    assert "自定义公司" in names


@pytest.mark.asyncio
async def test_response_includes_rubric_type(client: AsyncClient, session_factory):
    """Test that response includes rubric_type field."""
    # Seed test data
    async with session_factory() as s:
        s.add(CompanyStyle(
            name="某公司", rubric_type="faang", is_builtin=True,
            interviewer_style_tags=[], preferred_question_types=[],
            sample_questions=[], prompt_context_text="ctx",
        ))
        s.add(CompanyStyle(
            name="TCL", rubric_type="tcl_l2", is_builtin=True,
            interviewer_style_tags=[], preferred_question_types=[],
            sample_questions=[], prompt_context_text="ctx",
        ))
        await s.commit()

    resp = await client.get("/api/company-styles?builtin=true")
    assert resp.status_code == 200
    for item in resp.json():
        assert "rubric_type" in item, f"rubric_type missing in {item}"

    # Verify correct values
    items_by_name = {s["name"]: s for s in resp.json()}
    assert items_by_name["某公司"]["rubric_type"] == "faang"
    assert items_by_name["TCL"]["rubric_type"] == "tcl_l2"
