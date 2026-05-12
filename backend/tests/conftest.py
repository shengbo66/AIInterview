"""Test fixtures: in-memory SQLite + AWS mocks."""
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.clients import s3_audio
from app.db import get_session
from app.main import app
from app.models import Base, CompanyStyle


@pytest_asyncio.fixture
async def engine():
    # StaticPool: reuse a single connection so all async sessions share the
    # same in-memory database. Without this, aiosqlite opens a fresh
    # connection per checkout and each one gets an independent (empty) :memory: db.
    from sqlalchemy.pool import StaticPool

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def db_with_company(session_factory):
    """Seed a minimal company CompanyStyle and return the session_factory."""
    async with session_factory() as s:
        cs = CompanyStyle(
            name="H公司",
            interviewer_style_tags=["结构化"],
            preferred_question_types=["技术深度"],
            sample_questions=["介绍一个射频项目", "阻抗匹配的重要性"],
            prompt_context_text="H公司面试评估四大维度：技术深度、问题解决、沟通协作、文化契合。",
            is_builtin=True,
        )
        s.add(cs)
        await s.commit()
    return session_factory


@pytest.fixture
def mock_s3_upload(monkeypatch):
    """Mock only s3_audio.upload (for bidi_interview_session tests)."""
    up = AsyncMock(side_effect=lambda key, data, content_type="audio/pcm": key)
    monkeypatch.setattr("app.services.bidi_interview_session.s3_audio.upload", up)
    return up


@pytest.fixture
def mock_s3(monkeypatch):
    """Mock all S3 client calls — no real AWS in tests."""
    upload = AsyncMock(side_effect=lambda key, data, content_type="audio/webm": key)
    presign = AsyncMock(return_value="https://s3.example.com/presigned?sig=abc")
    delete = AsyncMock(return_value=None)
    monkeypatch.setattr(s3_audio, "upload", upload)
    monkeypatch.setattr(s3_audio, "presign_get", presign)
    monkeypatch.setattr(s3_audio, "delete_many", delete)
    return {"upload": upload, "presign": presign, "delete": delete}


@pytest_asyncio.fixture
async def client(session_factory, mock_s3) -> AsyncIterator[AsyncClient]:
    async def _override() -> AsyncIterator[AsyncSession]:
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
