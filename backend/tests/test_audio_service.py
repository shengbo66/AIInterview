"""Tests for audio_service: presigned URL delegation."""
import pytest

from app.models import Answer, Question
from app.services import audio_service, record_service


async def test_get_segment_url_happy_path(db, mock_s3):
    iv = await record_service.create_interview(db, company_name="X", role_title="Y")
    q = Question(
        interview_id=iv.id, order_index=0, question_text="q",
        question_audio_s3_key="key/q0.webm",
    )
    db.add(q)
    await db.flush()
    db.add(Answer(question_id=q.id, user_audio_s3_key="key/a0.webm", transcript_text=""))
    await db.commit()

    url, ttl = await audio_service.get_segment_url(db, iv.id, 0)
    assert url.startswith("https://")
    assert ttl > 0
    mock_s3["presign"].assert_awaited_once_with("key/q0.webm")


async def test_get_segment_url_invalid_index(db, mock_s3):
    iv = await record_service.create_interview(db, company_name="X", role_title="Y")
    with pytest.raises(record_service.NotFoundError):
        await audio_service.get_segment_url(db, iv.id, 0)
