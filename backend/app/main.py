"""FastAPI app entrypoint."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import verify_token
from app.config import settings
import app.db as _db_module
from app.logging_config import setup_logging
from app.routers import audio, company_styles, demo_bidi, health, interviews
from app.seed.company_styles import seed_if_empty as seed_company_styles
from app.seed.tcl_style import seed_if_empty as seed_tcl

setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with _db_module.SessionLocal() as session:
        await seed_company_styles(session)
        await seed_tcl(session)
    yield


app = FastAPI(title="Interviewer API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth requirement:
#   - /api/health: no auth (public for healthchecks)
#   - /api/* (other): JWT Bearer required
#   - /ws/* : JWT via ?token=... query param (handled in demo_bidi)
AUTH = [Depends(verify_token)]

app.include_router(health.router)
app.include_router(company_styles.router, dependencies=AUTH)
app.include_router(interviews.router, dependencies=AUTH)
app.include_router(audio.router, dependencies=AUTH)
app.include_router(demo_bidi.router)
