"""CompanyStyle service: list + create-from-upload."""
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CompanyStyle

MAX_UPLOAD_BYTES = 1 * 1024 * 1024  # 1 MB JSON


class ValidationError(Exception):
    pass


async def list_styles(db: AsyncSession, builtin_only: bool = False) -> list[CompanyStyle]:
    q = select(CompanyStyle)
    if builtin_only:
        q = q.where(CompanyStyle.is_builtin.is_(True))
    res = await db.execute(q.order_by(CompanyStyle.created_at.desc()))
    return list(res.scalars().all())


def _validate_payload(data: dict) -> None:
    required = ["name", "interviewer_style_tags", "preferred_question_types"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ValidationError(f"missing required fields: {missing}")
    if not isinstance(data["name"], str) or not data["name"].strip():
        raise ValidationError("name must be a non-empty string")
    for list_field in ("interviewer_style_tags", "preferred_question_types", "sample_questions"):
        if list_field in data and not isinstance(data[list_field], list):
            raise ValidationError(f"{list_field} must be a list")


async def create_from_upload(
    db: AsyncSession, raw: bytes, created_by: str | None = None
) -> CompanyStyle:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValidationError(f"file too large: {len(raw)} > {MAX_UPLOAD_BYTES}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValidationError(f"invalid JSON: {e}") from e
    _validate_payload(data)

    cs = CompanyStyle(
        name=data["name"].strip(),
        interviewer_style_tags=data.get("interviewer_style_tags", []),
        preferred_question_types=data.get("preferred_question_types", []),
        sample_questions=data.get("sample_questions", []),
        prompt_context_text=data.get("prompt_context_text", ""),
        is_builtin=False,
        created_by=created_by,
    )
    db.add(cs)
    await db.commit()
    await db.refresh(cs)
    return cs
