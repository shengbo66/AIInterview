# unit-1 Code Generation Plan

**Unit**: unit-1 backend-core
**Scope**: FastAPI 骨架 + SQLite (WAL) + Alembic + CompanyStyle/Record/Audio services + shared/eval_core 提取 + 基础 REST API
**Non-goals**: WebSocket endpoint (unit-2), EvaluationService (unit-3), 前端 (unit-4/5)

---

## 1. Directory Layout

```
shared/                        # NEW: 共享纯逻辑（POC + backend 共用）
├── __init__.py
└── eval_core/
    ├── __init__.py
    ├── rubric.py              # 从 poc/ 迁入
    ├── prompt_template.py     # 从 poc/ 迁入
    ├── voice_features.py      # 从 poc/ 迁入
    ├── utils.py               # 从 poc/ 迁入
    └── tests/                 # 从 poc/tests/ 迁入

backend/                       # NEW: MVP 后端
├── pyproject.toml             # Python 3.12 锁定 + deps + ruff 配置
├── .env.example
├── Dockerfile
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 0001_initial.py    # 首次迁移
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app + startup/shutdown
│   ├── config.py              # Settings from env
│   ├── db.py                  # SQLAlchemy engine, session
│   ├── models.py              # Interview/Question/Answer/Evaluation/CompanyStyle
│   ├── schemas.py             # Pydantic DTOs for API
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── bedrock_claude.py  # Claude Sonnet wrapper (async)
│   │   └── s3_audio.py        # S3 upload + presign
│   ├── services/
│   │   ├── __init__.py
│   │   ├── record_service.py       # Interview CRUD + cascade delete
│   │   ├── company_style_service.py
│   │   └── audio_service.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── health.py
│   │   ├── interviews.py
│   │   ├── company_styles.py
│   │   └── audio.py
│   ├── seed/
│   │   └── company_styles.py  # 3 个内置公司
│   └── errors.py              # Structured error helpers
└── tests/
    ├── __init__.py
    ├── conftest.py            # Test DB fixture
    ├── test_record_service.py
    ├── test_company_style_service.py
    ├── test_audio_service.py
    └── test_api_smoke.py      # Integration: health + CRUD flow
```

**代码量预估**: ~900-1100 行 Python (含测试)

---

## 2. Tasks Checklist

### Part A: 基础设施 + shared/eval_core 提取
- [ ] A1. 创建 `shared/eval_core/` 目录结构
- [ ] A2. 从 `poc/` 迁移 rubric.py / prompt_template.py / voice_features.py / utils.py 到 `shared/eval_core/`
- [ ] A3. 从 `poc/tests/` 迁移 test_*.py 到 `shared/eval_core/tests/`
- [ ] A4. 更新 `poc/` 的 import: 改为 `from shared.eval_core import ...`（保持 POC 可跑）
- [ ] A5. 验证迁移：`cd shared && pytest` + `cd poc && python run_verification.py` 都还通过

### Part B: backend 骨架
- [ ] B1. `backend/pyproject.toml` — Python 3.12, fastapi, sqlalchemy[asyncio], alembic, aiosqlite, pydantic, boto3, ruff
- [ ] B2. `backend/.env.example` + `backend/Dockerfile` (Python 3.12-slim + local dev)
- [ ] B3. `app/config.py` — Settings（region / S3 bucket / model IDs / DB path）
- [ ] B4. `app/main.py` — FastAPI app + WAL pragma on startup + routers register
- [ ] B5. `app/errors.py` — 统一 error response helper

### Part C: DB 层
- [ ] C1. `app/db.py` — async engine + session factory
- [ ] C2. `app/models.py` — 5 张表 + 新增 bidi_* 字段
- [ ] C3. `alembic.ini` + `alembic/env.py` (async 配置)
- [ ] C4. `alembic/versions/0001_initial.py` — auto-gen from models
- [ ] C5. `app/seed/company_styles.py` — 3 个内置（字节/Amazon/腾讯）+ startup hook 自动 seed

### Part D: Clients
- [ ] D1. `app/clients/bedrock_claude.py` — 参考 poc/claude_client.py，改为 async (aioboto3 或 asyncio.to_thread)
- [ ] D2. `app/clients/s3_audio.py` — async upload + presign GET URL

### Part E: Services
- [ ] E1. `app/services/record_service.py` — Interview 创建/查询/删除（含 S3 cascade）
- [ ] E2. `app/services/company_style_service.py` — list + upload (multipart)
- [ ] E3. `app/services/audio_service.py` — 生成 presigned URL

### Part F: API Routers
- [ ] F1. `app/schemas.py` — Pydantic request/response models
- [ ] F2. `app/routers/health.py` — `GET /api/health`
- [ ] F3. `app/routers/company_styles.py` — GET list, POST upload
- [ ] F4. `app/routers/interviews.py` — POST/GET list/GET detail/DELETE
- [ ] F5. `app/routers/audio.py` — `GET /api/interviews/{id}/audio/{segment_idx}`

### Part G: 测试
- [ ] G1. `tests/conftest.py` — in-memory SQLite fixture, async client
- [ ] G2. `test_record_service.py` — cascade delete 逻辑（可不调 S3，mock）
- [ ] G3. `test_company_style_service.py` — upload 文件大小/格式校验
- [ ] G4. `test_audio_service.py` — presign URL 参数（boto3 可本地生成，不实际调 AWS）
- [ ] G5. `test_api_smoke.py` — `/api/health` + 创建→list→get→delete 流程

### Part H: 验证 & CI
- [ ] H1. 跑 `pytest backend/tests/` 全绿
- [ ] H2. 本地起 `uvicorn app.main:app` + curl 健康检查
- [ ] H3. `.github/workflows/ci.yml` — pytest on push (shared + backend)
- [ ] H4. 跑 `ruff check backend/` pass

---

## 3. Key Design Decisions

| 决策 | 选择 | 理由 |
|---|---|---|
| HTTP client to AWS | **boto3 sync 包在 `asyncio.to_thread`** | aioboto3 有维护问题；to_thread 稳定且够用 |
| 测试 DB | SQLite in-memory (`sqlite+aiosqlite:///:memory:`) | 零依赖，快 |
| S3 测试 | 不调真实 AWS，mock client | 避免 CI 钱 |
| Bedrock 测试 | 不调真实 AWS，unit-3 集成测试再调 | 同上 |
| Dockerfile | `python:3.12-slim` + pip install | 简单，<200MB |
| ruff | `E,F,I,UP,B,SIM,RUF` 基础规则 + 120 char | 生产级默认 |

---

## 4. Execution Order

按 **6 小步** 实施（我每步一次回复，避免超时）：

| Step | Parts | 目标 |
|---|---|---|
| 1 | A (eval_core 迁移) + H4 (ruff) | 先验证 shared/ 重构不破坏 POC |
| 2 | B + C1-C2 | backend 骨架 + DB models |
| 3 | C3-C5 | Alembic + seed |
| 4 | D + E | Clients + Services |
| 5 | F | Routers |
| 6 | G + H (剩余) | 测试 + CI + 本地验证 |

每步结束后：`pytest` + `ruff check` 必须通过才推进。

---

## 5. Approval

回复 `approve` 按以上计划开始 Step 1；或指出要调整的项。
