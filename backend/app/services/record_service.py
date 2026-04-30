"""Interview record CRUD + cascade S3 audio delete."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clients import s3_audio
from app.models import CompanyStyle, Interview, Question


class NotFoundError(Exception):
    pass


async def create_interview(
    db: AsyncSession,
    *,
    company_name: str,
    role_title: str,
    company_style_id: str | None = None,
    language: str = "zh",
    duration_min: int = 45,
    question_count_target: int = 8,
    mode: str = "strict",
    resume_context: str | None = None,
) -> Interview:
    if company_style_id:
        cs = await db.get(CompanyStyle, company_style_id)
        if cs is None:
            raise NotFoundError(f"CompanyStyle {company_style_id} not found")
    iv = Interview(
        company_name=company_name,
        role_title=role_title,
        company_style_id=company_style_id,
        language=language,
        duration_min=duration_min,
        question_count_target=question_count_target,
        mode=mode,
        resume_context=resume_context,
    )
    db.add(iv)
    await db.commit()
    await db.refresh(iv)
    return iv


async def list_interviews(db: AsyncSession, limit: int = 100) -> list[Interview]:
    res = await db.execute(
        select(Interview).order_by(Interview.created_at.desc()).limit(limit)
    )
    return list(res.scalars().all())


async def get_interview(db: AsyncSession, interview_id: str) -> Interview:
    res = await db.execute(
        select(Interview)
        .where(Interview.id == interview_id)
        .options(
            selectinload(Interview.questions).selectinload(Question.answer),
            selectinload(Interview.evaluations),
        )
    )
    iv = res.scalar_one_or_none()
    if iv is None:
        raise NotFoundError(f"Interview {interview_id} not found")
    return iv


async def delete_interview(db: AsyncSession, interview_id: str) -> None:
    """Delete interview + cascade (questions/answers/evaluations via FK) + S3 audio."""
    iv = await get_interview(db, interview_id)
    # collect all audio keys before DB delete
    keys: list[str] = []
    for q in iv.questions:
        if q.question_audio_s3_key:
            keys.append(q.question_audio_s3_key)
        if q.answer and q.answer.user_audio_s3_key:
            keys.append(q.answer.user_audio_s3_key)
    await db.delete(iv)
    await db.commit()
    # S3 cascade after DB commit; best-effort
    await s3_audio.delete_many(keys)


async def collect_audio_keys(db: AsyncSession, interview_id: str) -> list[str]:
    """Helper: ordered list of all audio keys for an interview (question+answer interleaved)."""
    iv = await get_interview(db, interview_id)
    keys: list[str] = []
    for q in sorted(iv.questions, key=lambda x: x.order_index):
        if q.question_audio_s3_key:
            keys.append(q.question_audio_s3_key)
        if q.answer and q.answer.user_audio_s3_key:
            keys.append(q.answer.user_audio_s3_key)
    return keys


# Answer access helper for audio_service
async def get_answer_audio_key(
    db: AsyncSession, interview_id: str, segment_idx: int
) -> str:
    """Return S3 key for a specific segment (0-based index into interleaved audio list)."""
    keys = await collect_audio_keys(db, interview_id)
    if segment_idx < 0 or segment_idx >= len(keys):
        raise NotFoundError(f"segment_idx {segment_idx} out of range (0..{len(keys) - 1})")
    return keys[segment_idx]
