"""Tests for record_service: CRUD + cascade S3 delete."""
import pytest

from app.models import Answer, Question
from app.services import record_service


async def _make_interview_with_audio(db):
    iv = await record_service.create_interview(
        db, company_name="H公司", role_title="RF Intern", language="zh"
    )
    q = Question(
        interview_id=iv.id, order_index=0, question_text="q1",
        question_audio_s3_key=f"interviews/{iv.id}/q0.webm",
    )
    db.add(q)
    await db.flush()
    db.add(Answer(
        question_id=q.id, transcript_text="a1", duration_sec=5.0,
        user_audio_s3_key=f"interviews/{iv.id}/a0.webm",
    ))
    await db.commit()
    return iv


async def test_create_and_get(db):
    iv = await record_service.create_interview(
        db, company_name="H公司", role_title="RF Intern"
    )
    fetched = await record_service.get_interview(db, iv.id)
    assert fetched.id == iv.id
    assert fetched.company_name == "H公司"


async def test_get_not_found(db):
    with pytest.raises(record_service.NotFoundError):
        await record_service.get_interview(db, "nonexistent")


async def test_create_with_invalid_company_style_id(db):
    with pytest.raises(record_service.NotFoundError):
        await record_service.create_interview(
            db, company_name="X", role_title="Y", company_style_id="bogus"
        )


async def test_list_ordered_desc(db):
    iv1 = await record_service.create_interview(db, company_name="A", role_title="a")
    iv2 = await record_service.create_interview(db, company_name="B", role_title="b")
    items = await record_service.list_interviews(db)
    assert [i.id for i in items[:2]] == [iv2.id, iv1.id]


async def test_delete_cascades_to_s3(db, mock_s3):
    iv = await _make_interview_with_audio(db)
    await record_service.delete_interview(db, iv.id)
    # DB row gone
    with pytest.raises(record_service.NotFoundError):
        await record_service.get_interview(db, iv.id)
    # S3 delete called with both keys
    mock_s3["delete"].assert_awaited_once()
    keys = mock_s3["delete"].await_args.args[0]
    assert len(keys) == 2
    assert any("q0.webm" in k for k in keys)
    assert any("a0.webm" in k for k in keys)


async def test_collect_audio_keys_ordered(db):
    iv = await _make_interview_with_audio(db)
    keys = await record_service.collect_audio_keys(db, iv.id)
    # q then a for order_index=0
    assert len(keys) == 2
    assert "q0.webm" in keys[0]
    assert "a0.webm" in keys[1]


async def test_get_answer_audio_key_out_of_range(db):
    iv = await _make_interview_with_audio(db)
    with pytest.raises(record_service.NotFoundError):
        await record_service.get_answer_audio_key(db, iv.id, 99)
