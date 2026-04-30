"""Interview endpoints."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors
from app.db import get_session
from app.schemas import InterviewCreate, InterviewDetail, InterviewSummary
from app.services import record_service

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


@router.post("", response_model=InterviewDetail, status_code=201)
async def create_interview(
    body: InterviewCreate, db: AsyncSession = Depends(get_session)
) -> InterviewDetail:
    try:
        iv = await record_service.create_interview(db, **body.model_dump())
    except record_service.NotFoundError as e:
        raise errors.not_found(str(e)) from e
    # reload with eager-loaded relationships for the response shape
    iv = await record_service.get_interview(db, iv.id)
    return InterviewDetail.model_validate(iv)


@router.get("", response_model=list[InterviewSummary])
async def list_interviews(
    limit: int = 100, db: AsyncSession = Depends(get_session)
) -> list[InterviewSummary]:
    items = await record_service.list_interviews(db, limit=limit)
    return [InterviewSummary.model_validate(i) for i in items]


@router.get("/{interview_id}", response_model=InterviewDetail)
async def get_interview(
    interview_id: str, db: AsyncSession = Depends(get_session)
) -> InterviewDetail:
    try:
        iv = await record_service.get_interview(db, interview_id)
    except record_service.NotFoundError as e:
        raise errors.not_found(str(e)) from e
    return InterviewDetail.model_validate(iv)


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(
    interview_id: str, db: AsyncSession = Depends(get_session)
) -> None:
    try:
        await record_service.delete_interview(db, interview_id)
    except record_service.NotFoundError as e:
        raise errors.not_found(str(e)) from e
