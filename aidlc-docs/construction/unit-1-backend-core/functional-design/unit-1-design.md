# unit-1 backend-core — Functional Design (Minimal)

**Scope**: FastAPI 骨架 + DB + 基础业务 Service + REST API（不含 WebSocket 面试流、不含评估执行）
**Non-goals**: WebSocket endpoint（unit-2），评估执行逻辑（unit-3），前端（unit-4/5）

---

## 1. Delivered Components

### API Endpoints (REST)

| Method | Path | Purpose | Response |
|---|---|---|---|
| GET | `/api/health` | Liveness | `{"status": "ok"}` |
| GET | `/api/company-styles` | List all company styles (builtin + user) | `[{id, name, interviewer_style_tags, is_builtin, ...}]` |
| POST | `/api/company-styles/upload` | Upload custom style (multipart: file + name) | `{id, name, ...}` |
| POST | `/api/interviews` | Create interview record (pre-session) | `{id, ws_url}` — ws_url is placeholder; unit-2 implements |
| GET | `/api/interviews` | List interviews (paginated) | `{items, total, offset, limit}` |
| GET | `/api/interviews/{id}` | Get interview + related Q&A + Evaluation | full detail object |
| DELETE | `/api/interviews/{id}` | Delete interview + cascade audio | 204 |
| GET | `/api/interviews/{id}/audio/{segment_idx}` | S3 pre-signed URL for playback | `{url, ttl_sec}` |

### Services (business logic layer)

- **RecordService**: Interview CRUD, cascade delete to S3 audio
- **CompanyStyleService**: Builtin seed + user upload management
- **AudioService**: S3 upload + pre-signed URL generation

### AWS Clients

- **BedrockClient**: Reuse POC `claude_client.py` pattern — wrapper for Bedrock Claude Sonnet invoke
- **S3Client**: Upload, download, presign

### Database

- SQLite file `interviewer.db` at workspace root (MVP), WAL mode enabled
- SQLAlchemy 2.0 async + Alembic migrations
- Tables (per Application Design): `interview`, `question`, `answer`, `evaluation`, `company_style`
- **User table NOT in unit-1 MVP** (matches FR: MVP is single-user, no auth)

---

## 2. Key Design Decisions (inherited from Application Design)

| Decision | Choice | Source |
|---|---|---|
| Framework | FastAPI async | ADR-001 |
| ORM | SQLAlchemy 2.0 async + Alembic | Req §5 |
| DB | SQLite (WAL) | Req §5.1 |
| Bedrock region | us-east-1 | Req §5.1 |
| Audio format on S3 | WebM/Opus (user) + MP3 (AI) | Req §5.1 |
| Pre-signed URL TTL | 1 hour (default, configurable) | New |
| Seed CompanyStyles | 3 builtin: 字节 / Amazon / 腾讯 | FR-1.2 |
| Deploy target | ECS Fargate us-east-1 (MVP prod); local for dev | ADR-001 |

---

## 3. Business Rules

**BR-1 Interview creation**:
- Client posts `{company_style_id?, company_name, role_title, language, duration_min, question_count_target, resume_context?}`
- Server creates Interview with `status="in_progress"`, `started_at=null` (set by unit-2 when WS connects)
- Returns `id` + placeholder `ws_url` (format: `/ws/interview/{id}`)
- `resume_context` is stored on Interview row directly (temp, not a separate table)

**BR-2 Interview delete**:
- Cascade delete all Questions, Answers, Evaluation(s) for that interview
- Enumerate S3 objects under `interviews/{id}/` prefix and delete
- Idempotent (delete of non-existent returns 204)

**BR-3 Company style upload**:
- Accept `.md` or `.txt` file, max 50KB (FR-1.3)
- Parse minimally: file content → `prompt_context_text`; other structured fields default to empty/null
- `is_builtin=false`, `created_by=null` (MVP no auth)

**BR-4 Audio pre-signed URL**:
- Verify `segment_idx` maps to an Answer row where `user_audio_s3_key` is set
- Generate GET pre-signed URL, TTL=3600s
- Only accessible via interview detail path (no cross-interview enumeration)

**BR-5 Database initialization**:
- On first `uvicorn` boot: run Alembic `upgrade head`
- Seed builtin CompanyStyles if table empty

---

## 4. Concurrency & Error Handling

- SQLite WAL mode set via `PRAGMA journal_mode=WAL` on startup
- Single uvicorn worker (MVP) — avoids SQLite multi-writer contention
- S3 failures: log + 500 response with structured error `{"error": "s3_unavailable", "retry_after_sec": 30}`
- Bedrock client not called in unit-1 (deferred to unit-2/3) — just the wrapper class ready

---

## 5. Out-of-Scope (explicit)

- ❌ WebSocket endpoint `/ws/interview/{id}` — unit-2
- ❌ InterviewService.complete / abandon state transitions — unit-2
- ❌ QuestionService — unit-2 (question generation via Claude)
- ❌ EvaluationService — unit-3
- ❌ PDF export (FR-4.3) — Should priority, could defer
- ❌ Auth, rate limiting, CORS prod hardening — MVP不做或 Beta

---

## 6. Acceptance (for unit-1 completion)

- [ ] `uvicorn main:app` starts successfully, `/api/health` returns 200
- [ ] Alembic migrations create all 5 tables
- [ ] 3 builtin CompanyStyles seeded on fresh DB
- [ ] POST/GET/DELETE flow for interviews works end-to-end (manual curl or integration test)
- [ ] Upload custom style works, retrievable via list
- [ ] Pre-signed URL returns valid S3 URL that plays audio (manual check)
- [ ] Unit tests for pure-logic services (schema validation, cascade logic)
- [ ] Ready for unit-2 (WS) and unit-3 (evaluation) to import and extend

---

## 7. Integration notes for unit-2 (Strands BidiAgent) — NEW

Pre-POC (2026-04-26) validated Strands Agents `BidiAgent` + Nova Sonic. Data model decisions for unit-1:

### 7.1 Q-A segmentation — direction chosen: **keep current Q-A schema**

Strands bidi session emits fine-grained events (`bidi_audio_input`, `bidi_audio_stream`, `bidi_usage`, `bidi_turn_end` etc.). unit-2 is responsible for **segmenting the stream into Q-A pairs** before writing to DB:

- On AI speech end → create a `Question` row with generated text + audio S3 key
- On user speech end (VAD / turn_end) → create an `Answer` row linked to the last open Question
- Buffer partial audio frames; upload a consolidated file to S3 once the turn closes
- `transcript_text` accumulates from multiple text_delta events within a single user turn

### 7.2 Data model additions for Nova Sonic cost tracking

Add to `Interview` table:

```
bidi_tokens_total   INTEGER   DEFAULT 0   -- running total from bidi_usage events
bidi_cost_usd       REAL      DEFAULT 0   -- computed from tokens per Bedrock pricing
bidi_started_at     TIMESTAMP              -- set when WS connects
bidi_ended_at       TIMESTAMP              -- set on completion/abandon
```

Rationale: Pre-POC observed Nova Sonic tokens accumulate **per session duration** (not per turn). Total cost is a per-Interview fact, not per-Answer. Evaluation-related cost stays on `Evaluation.evaluation_cost`.

### 7.3 Minimal `BedrockClient` scope for unit-1

unit-1 ships only the **Claude Sonnet** wrapper (used by unit-3 evaluation). The Nova Sonic integration lives in unit-2 as `InterviewAgent` adapter wrapping `strands.experimental.bidi.BidiAgent` — keeps Strands experimental API isolated.
