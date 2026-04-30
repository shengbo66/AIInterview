"""Audio segment presigned-URL endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors
from app.db import get_session
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
