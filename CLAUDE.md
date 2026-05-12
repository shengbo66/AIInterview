# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI voice interview platform. A user speaks into the browser microphone; the audio is streamed over WebSocket to FastAPI, which proxies it through AWS Nova Sonic (bidirectional AI speech) and simultaneously runs evaluation (Claude Sonnet 4.5 + Transcribe + Comprehend). Results are stored in SQLite and rendered in the Next.js UI.

## Commands

### Frontend (`cd frontend`)
```bash
npm run dev          # Dev server at http://localhost:3000
npm run build        # Production build
npm test             # Run vitest suite (~200ms, 6 tests)
npm run typecheck    # TypeScript check
```

### Backend (`cd backend`)
```bash
source .venv/bin/activate          # Activate venv (uv)
uv pip install -e ".[dev]"         # Install deps
alembic upgrade head               # Apply DB migrations
uvicorn app.main:app --reload --port 8000  # Dev server
pytest -q                          # Run 128 tests (~11s)
```

### Single test
```bash
# Backend
pytest tests/services/test_voice_analyzer.py -q

# Frontend
npx vitest run src/lib/audio-codec.test.ts
```

### Smoke test (WebSocket connectivity, ~30s)
```bash
python backend/scripts/ws_smoke.py --tone 0
```

## Architecture

### Data Flow
```
Browser (Next.js) ──WebSocket──► FastAPI ──BidiStream──► Nova Sonic (AWS Bedrock)
                                    │
                                    ├──► Transcribe (zh-CN → transcript)
                                    ├──► Comprehend (sentiment)
                                    ├──► Claude Sonnet 4.5 (stage1/stage2 eval)
                                    ├──► SQLite WAL (interviews, Q&A, scores)
                                    └──► S3 (audio files, JSON exports)
```

### Key Backend Modules

| File | Purpose |
|------|---------|
| `routers/demo_bidi.py` | WebSocket endpoint; Nova Sonic bootstrap + Q/A lifecycle (~400 LOC) |
| `services/bidi_interview_session.py` | Interview state machine, S3 upload, session teardown |
| `services/evaluation_service.py` | Orchestrates Claude stage1/stage2 + voice metrics aggregation |
| `services/voice_analyzer.py` | 20 voice metrics, pure stdlib (no numpy) |
| `shared/eval_core/` | Rubric formulas and Claude prompts (shared between service and tests) |
| `clients/` | Thin adapters: Bedrock, Transcribe, Comprehend, S3 |
| `models.py` | SQLAlchemy 2.0 async: Interview, Question, Answer, Evaluation, CompanyStyle |

### Key Frontend Modules

| File | Purpose |
|------|---------|
| `app/page.tsx` | Main interview UI; AudioWorklet capture, PCM codec, WebSocket client (~1000 LOC) |
| `app/history/[id]/page.tsx` | Interview detail with audio playback and score breakdown |
| `lib/auth.ts` | Cognito Hosted UI + automatic JWT refresh |
| `components/AuthGuard.tsx` | Route protection; bypassed when `COGNITO_USER_POOL_ID` is unset |
| `lib/audio-codec.ts` | PCM16 LE ↔ base64 encode/decode |

### Database Schema (SQLite WAL)
5 tables: `interview` → `question` → `answer` → `evaluation` (per-question + overall), `company_style` (role templates). Company styles auto-seed on startup if empty.

## Critical Implementation Details

**Language policy**: All AI-generated content (interview questions, evaluation reports, UI text, code comments) must be in **Chinese (中文) or English only**. Never output Korean, Japanese, or other languages regardless of model inference tendencies.

**Nova Sonic bootstrap**: Must inject `hello.pcm` to prevent the AI from speaking first (SDK limitation). Endpoint sensitivity is set to `LOW` for V2 turn detection (reduced from MEDIUM to avoid false end-of-turn detection on natural speech pauses).

**Audio format throughout**: PCM16 LE, mono, 16kHz. WebSocket carries base64-encoded chunks + JSON metadata. Transcribe requires a 44-byte WAV header wrapper — raw PCM is rejected.

**Strands version lock**: `strands-agents[bidi-all]>=1.37,<2.0` — do not upgrade without testing Nova Sonic bidi flow end-to-end.

**Session GC prevention**: Task references for async Nova Sonic streams must be held in a module-level set; Python will garbage-collect them otherwise mid-interview.

**Auth toggle**: Auth is disabled locally by default. Set `COGNITO_USER_POOL_ID` in `backend/.env` to enable Cognito JWT validation.

**Next.js version**: This project uses Next.js 16 (see `frontend/AGENTS.md` for breaking changes vs. v15).

## Evaluation System

20 metrics split across three dimensions:
- **Content** (50%): STAR structure, specificity, impact quantification, leadership, problem-solving, clarity
- **Expression** (30%): 5-level scale (chaotic → outstanding)  
- **Voice** (20%): Speaking speed, pause patterns, filler words, speaking ratio, first-response delay, hesitation frequency, volume stability, pronunciation clarity, sentiment

Evaluation runs in two Claude stages (stage1 = per-answer scoring, stage2 = holistic synthesis) plus voice analysis from Transcribe timestamps.

## Deployment

- **Production**: EC2 ap-northeast-1 (Tokyo), systemd services `interviewer-backend` / `interviewer-frontend` / `caddy`
- **Reverse proxy**: Caddy `:80` → `:8000` (API) and `:3000` (frontend)
- **CDN**: CloudFront HTTPS (d1hlahtkv3v1q6.cloudfront.net)
- **Cost per interview**: ~$0.15 (Nova Sonic $0.01, Claude $0.12, Transcribe $0.024, Comprehend + S3 ~$0.002)
