"""FastAPI app entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import SessionLocal
from app.logging_config import setup_logging
from app.routers import audio, company_styles, demo_bidi, health, interviews
from app.seed.company_styles import seed_if_empty

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with SessionLocal() as session:
        await seed_if_empty(session)
    yield


app = FastAPI(title="Interviewer API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(company_styles.router)
app.include_router(interviews.router)
app.include_router(audio.router)
app.include_router(demo_bidi.router)
