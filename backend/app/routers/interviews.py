"""Interview endpoints."""
import asyncio

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


@router.post("/{interview_id}/evaluate", status_code=202)
async def trigger_evaluation(
    interview_id: str, db: AsyncSession = Depends(get_session)
) -> dict:
    """Manually trigger (or re-trigger) evaluation for an interview."""
    from app.db import SessionLocal
    from app.services.evaluation_service import evaluate_interview

    iv = await record_service.get_interview(db, interview_id)
    if iv.status not in ("completed", "evaluation_failed"):
        raise errors.bad_request(f"Cannot evaluate interview in status '{iv.status}'")
    iv.status = "evaluating"
    await db.commit()
    asyncio.create_task(evaluate_interview(SessionLocal, interview_id))  # noqa: RUF006
    return {"status": "evaluation_started", "interview_id": interview_id}
