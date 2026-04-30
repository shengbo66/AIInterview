"""Tests for company_style_service: validation + upload."""
import json

import pytest

from app.services import company_style_service


async def test_list_empty(db):
    assert await company_style_service.list_styles(db) == []


async def test_create_from_upload_valid(db):
    payload = {
        "name": "测试公司",
        "interviewer_style_tags": ["严谨"],
        "preferred_question_types": ["STAR"],
        "sample_questions": ["q1"],
        "prompt_context_text": "ctx",
    }
    cs = await company_style_service.create_from_upload(
        db, json.dumps(payload).encode("utf-8")
    )
    assert cs.name == "测试公司"
    assert cs.is_builtin is False
    listed = await company_style_service.list_styles(db)
    assert len(listed) == 1


async def test_create_rejects_invalid_json(db):
    with pytest.raises(company_style_service.ValidationError, match="invalid JSON"):
        await company_style_service.create_from_upload(db, b"{not json")


async def test_create_rejects_missing_fields(db):
    raw = json.dumps({"name": "X"}).encode()
    with pytest.raises(company_style_service.ValidationError, match="missing"):
        await company_style_service.create_from_upload(db, raw)


async def test_create_rejects_empty_name(db):
    raw = json.dumps({
        "name": "  ",
        "interviewer_style_tags": [],
        "preferred_question_types": [],
    }).encode()
    with pytest.raises(company_style_service.ValidationError, match="name"):
        await company_style_service.create_from_upload(db, raw)


async def test_create_rejects_oversize(db):
    big = b"x" * (company_style_service.MAX_UPLOAD_BYTES + 1)
    with pytest.raises(company_style_service.ValidationError, match="too large"):
        await company_style_service.create_from_upload(db, big)


async def test_create_rejects_non_list_tags(db):
    raw = json.dumps({
        "name": "X",
        "interviewer_style_tags": "not-a-list",
        "preferred_question_types": [],
    }).encode()
    with pytest.raises(company_style_service.ValidationError, match="must be a list"):
        await company_style_service.create_from_upload(db, raw)
