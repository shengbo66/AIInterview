import pytest
from sqlalchemy import select

from app.models import CompanyStyle
from app.seed.tcl_style import seed_if_empty


@pytest.mark.asyncio
async def test_seed_inserts_tcl(db):
    count = await seed_if_empty(db)
    assert count == 1
    result = await db.execute(select(CompanyStyle).where(CompanyStyle.name == "TCL"))
    cs = result.scalar_one_or_none()
    assert cs is not None
    assert cs.rubric_type == "tcl_l2"
    assert cs.is_builtin is True
    assert len(cs.sample_questions) >= 5


@pytest.mark.asyncio
async def test_seed_is_idempotent(db):
    count1 = await seed_if_empty(db)
    count2 = await seed_if_empty(db)
    assert count1 == 1
    assert count2 == 0
    result = await db.execute(select(CompanyStyle).where(CompanyStyle.name == "TCL"))
    rows = result.scalars().all()
    assert len(rows) == 1
