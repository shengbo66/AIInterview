"""Audio segment presigned-URL endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors
from app.clients import s3_audio
from app.config import settings
from app.db import get_session
from app.models import Answer, Question
from app.schemas import AudioUrlResponse
from app.services import audio_service, record_service

router = APIRouter(prefix="/api/interviews", tags=["audio"])


@router.get("/{interview_id}/audio/{segment_idx}", response_model=AudioUrlResponse)
async def get_audio_url(
    interview_id: str, segment_idx: int, db: AsyncSession = Depends(get_session)
) -> AudioUrlResponse:
    try:
        url, ttl = await audio_service.get_segment_url(db, interview_id, segment_idx)
    except record_service.NotFoundError as e:
        raise errors.not_found(str(e)) from e
    return AudioUrlResponse(url=url, expires_in_sec=ttl)


@router.get(
    "/{interview_id}/questions/{question_id}/audio",
    response_model=AudioUrlResponse,
)
async def get_question_audio_url(
    interview_id: str,
    question_id: str,
    role: str = "assistant",
    db: AsyncSession = Depends(get_session),
) -> AudioUrlResponse:
    """Get presigned URL for a specific question's audio.

    role=assistant → AI question audio (question_audio_s3_key)
    role=user → user answer audio (answer.user_audio_s3_key)
    """
    q = (
        await db.execute(
            select(Question)
            .where(Question.id == question_id, Question.interview_id == interview_id)
        )
    ).scalar_one_or_none()
    if q is None:
        raise errors.not_found(f"Question {question_id} not found")

    if role == "user":
        a = (
            await db.execute(select(Answer).where(Answer.question_id == question_id))
        ).scalar_one_or_none()
        if a is None or not a.user_audio_s3_key:
            raise errors.not_found("No user audio for this question")
        key = a.user_audio_s3_key
    else:
        if not q.question_audio_s3_key:
            raise errors.not_found("No AI audio for this question")
        key = q.question_audio_s3_key

    url = await s3_audio.presign_get(key)
    return AudioUrlResponse(url=url, expires_in_sec=settings.presigned_url_ttl_sec)
