"""Audio service: generate presigned GET URLs for interview segments."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import s3_audio
from app.services import record_service


async def get_segment_url(
    db: AsyncSession, interview_id: str, segment_idx: int
) -> tuple[str, int]:
    """Return (presigned_url, expires_in_sec) for a given segment."""
    key = await record_service.get_answer_audio_key(db, interview_id, segment_idx)
    url = await s3_audio.presign_get(key)
    from app.config import settings

    return url, settings.presigned_url_ttl_sec
