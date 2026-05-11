"""Company style endpoints."""
from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app import errors
from app.db import get_session
from app.schemas import CompanyStyleOut
from app.services import company_style_service

router = APIRouter(prefix="/api/company-styles", tags=["company_styles"])


@router.get("", response_model=list[CompanyStyleOut])
async def list_company_styles(
    builtin: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
) -> list[CompanyStyleOut]:
    styles = await company_style_service.list_styles(db, builtin_only=builtin)
    return [CompanyStyleOut.model_validate(s) for s in styles]


@router.post("", response_model=CompanyStyleOut, status_code=201)
async def upload_company_style(
    file: UploadFile, db: AsyncSession = Depends(get_session)
) -> CompanyStyleOut:
    raw = await file.read()
    try:
        cs = await company_style_service.create_from_upload(db, raw)
    except company_style_service.ValidationError as e:
        if "too large" in str(e):
            raise errors.payload_too_large(str(e)) from e
        raise errors.bad_request(str(e)) from e
    return CompanyStyleOut.model_validate(cs)
