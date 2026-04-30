# Application Design — Components

**Scope**: Phase 1 MVP (Phase 0 POC 只是单脚本，不涉及组件设计)
**Date**: 2026-04-25

---

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Browser (Chrome 90+ / Safari 16+)                            │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Next.js 15 Frontend                                     ││
│  │  • Setup Page  • Interview Page  • History/Detail Page  ││
│  │  • MediaRecorder (audio capture)                        ││
│  │  • WebSocket client (interview)                         ││
│  │  • REST client (rest)                                   ││
│  └─────────────────────────────────────────────────────────┘│
└────────┬──────────────────────────────────┬─────────────────┘
         │ WebSocket (audio stream)          │ HTTPS (REST)
         │ /ws/interview/{id}                │ /api/*
         ▼                                   ▼
┌─────────────────────────────────────────────────────────────┐
│ FastAPI Backend (ECS Fargate, us-east-1)                    │
│                                                               │
│ ┌──────────────┐  ┌───────────────┐  ┌──────────────────┐  │
│ │ WS Gateway   │  │ REST Gateway  │  │ Background Worker│  │
│ │ /ws/...      │  │ /api/...      │  │ (evaluation)     │  │
│ └──────┬───────┘  └───────┬───────┘  └────────┬─────────┘  │
│        │                  │                    │             │
│ ┌──────▼──────────────────▼────────────────────▼─────────┐ │
│ │ Service Layer                                           │ │
│ │  • InterviewService    • EvaluationService             │ │
│ │  • QuestionService     • CompanyStyleService           │ │
│ │  • RecordService       • AudioService                  │ │
│ └──────┬──────────────────┬────────────────────┬─────────┘ │
│        │                  │                    │             │
│ ┌──────▼───────┐  ┌──────▼────────┐  ┌───────▼──────────┐ │
│ │ BedrockClient│  │ TranscribeClient│  │ StorageAdapter  │ │
│ │ • Nova Sonic │  │ • CallAnalytics│  │ • SQLite (WAL) │ │
│ │ • Claude Sonnet│                  │  │ • S3           │ │
│ └──────┬───────┘  └───────┬────────┘  └────────┬─────────┘ │
└────────┼──────────────────┼────────────────────┼────────────┘
         │                  │                    │
         ▼                  ▼                    ▼
    ┌─────────┐        ┌──────────┐       ┌──────────────┐
    │ Bedrock │        │Transcribe│       │ SQLite + S3  │
    └─────────┘        └──────────┘       └──────────────┘
```

---

## 2. Component Inventory

### Frontend (Next.js 15)

| Component | Responsibility | Unit |
|---|---|---|
| **SetupPage** | 面试参数配置 + 简历/风格上传 | unit-4 |
| **InterviewPage** | 面试进行中 UI + WebSocket 客户端 + MediaRecorder | unit-4 |
| **WaitingPage** | "报告生成中" + 轮询评估状态 | unit-4 |
| **HistoryListPage** | 面试记录列表 | unit-5 |
| **InterviewDetailPage** | 面试详情 + 音频回放 + 评估报告 | unit-5 |
| **AudioCapture** (hook) | 封装 MediaRecorder + 权限管理 | unit-4 |
| **WebSocketClient** (hook) | 封装 WS 生命周期 + 重连策略 | unit-4 |
| **ApiClient** | 调用后端 REST API（OpenAPI 自动生成） | unit-4, unit-5 |
| **UI Components** | shadcn/ui + Framer Motion 动效组件 | unit-4, unit-5 |

### Backend (FastAPI)

| Component | Responsibility | Unit |
|---|---|---|
| **WS Gateway** | WebSocket endpoint `/ws/interview/{id}` 编排音频双向流 | unit-2 |
| **REST Gateway** | `/api/interviews/*`, `/api/company-styles/*`, `/api/health` | unit-1, unit-2 |
| **BackgroundWorker** | 面试结束后异步触发评估（asyncio Task） | unit-3 |
| **InterviewService** | 面试生命周期（创建/开始/结束/放弃） | unit-2 |
| **QuestionService** | 调用 Claude 动态生成问题（基于公司风格 + 简历 + 历史问答） | unit-2 |
| **EvaluationService** | 调用 Transcribe + Claude，生成评估报告（复用 POC 代码） | unit-3 |
| **RecordService** | 面试记录 CRUD + PDF 导出 + 删除级联 | unit-1 |
| **CompanyStyleService** | 内置风格 + 用户上传风格管理 | unit-1 |
| **AudioService** | S3 上传/下载、pre-signed URL 生成 | unit-1 |
| **BedrockClient** | 封装 Nova Sonic 双向流 + Claude invoke | unit-1 |
| **TranscribeClient** | 封装 Transcribe Call Analytics 调用 | unit-3 |
| **StorageAdapter** | SQLite (SQLAlchemy 2.0 async) + Alembic migrations | unit-1 |

---

## 3. Service Layer Contracts

### InterviewService

```python
class InterviewService:
    async def create(params: InterviewCreateParams) -> Interview
    async def start(interview_id: str) -> None  # 标记开始
    async def complete(interview_id: str) -> None  # 正常结束 + 触发评估
    async def abandon(interview_id: str, reason: str) -> None
    async def get(interview_id: str) -> Interview | None
    async def list(limit: int, offset: int) -> list[Interview]
    async def delete(interview_id: str) -> None  # 级联删除 S3 音频
```

### EvaluationService

```python
class EvaluationService:
    async def evaluate(interview_id: str) -> Evaluation  # 异步执行
    async def get_by_interview(interview_id: str) -> Evaluation | None
    async def retry(interview_id: str) -> Evaluation  # 失败后手动重试
```

### QuestionService

```python
class QuestionService:
    async def generate_next(
        interview_id: str,
        history: list[Q&A],
        company_style: CompanyStyle,
        resume_context: str | None,
    ) -> Question
```

### AudioService

```python
class AudioService:
    async def upload_segment(interview_id: str, segment_idx: int, pcm_data: bytes) -> str  # returns s3_key
    async def generate_playback_url(s3_key: str, ttl_sec: int = 3600) -> str
    async def delete_interview_audio(interview_id: str) -> None
```

---

## 4. API Contracts (REST + WS)

### REST APIs

| Method | Path | Purpose | Unit |
|---|---|---|---|
| `GET` | `/api/health` | 健康检查 | unit-1 |
| `GET` | `/api/company-styles` | 列表内置公司风格 | unit-1 |
| `POST` | `/api/company-styles/upload` | 上传自定义风格（form-data） | unit-1 |
| `POST` | `/api/interviews` | 创建面试 (returns id + ws_url) | unit-2 |
| `GET` | `/api/interviews` | 记录列表（分页） | unit-1 |
| `GET` | `/api/interviews/{id}` | 面试详情 | unit-1 |
| `DELETE` | `/api/interviews/{id}` | 删除记录 | unit-1 |
| `GET` | `/api/interviews/{id}/evaluation` | 评估报告 | unit-3 |
| `POST` | `/api/interviews/{id}/evaluation/retry` | 评估失败重试 | unit-3 |
| `GET` | `/api/interviews/{id}/audio/{segment_idx}` | 音频 pre-signed URL | unit-1 |
| `GET` | `/api/interviews/{id}/pdf` | 导出 PDF 报告 | unit-1 (Should) |

### WebSocket API

| Path | Purpose | Unit |
|---|---|---|
| `/ws/interview/{id}` | 面试音频双向流 | unit-2 |

**WebSocket 消息协议**（JSON over WS + binary frames 音频）：

```
Client → Server:
  { "type": "start", "interview_id": "..." }
  binary frame: WebM/Opus audio chunk
  { "type": "end_of_interview" }

Server → Client:
  { "type": "ai_speaking_start" }
  binary frame: PCM audio chunk (AI speech)
  { "type": "ai_speaking_end", "transcript": "..." }
  { "type": "user_transcript_partial", "text": "..." }
  { "type": "user_transcript_final", "text": "...", "question_id": "..." }
  { "type": "question_start", "question_id": "...", "order": 3 }
  { "type": "interview_complete" }
  { "type": "error", "code": "...", "message": "..." }
```

**完整的 OpenAPI spec** 将在 Code Generation 阶段由 FastAPI 自动生成。

---

## 5. Component Dependencies

```
Frontend components
  └→ ApiClient → REST Gateway → Service Layer → StorageAdapter / BedrockClient / TranscribeClient
  └→ WebSocketClient → WS Gateway → InterviewService → BedrockClient (Nova Sonic)
                                                     → QuestionService → BedrockClient (Claude)
                                                     → AudioService → S3

BackgroundWorker → EvaluationService → TranscribeClient
                                     → BedrockClient (Claude)
                                     → StorageAdapter
```

**无循环依赖**：Service → Client → External。
**Service 之间的依赖**：EvaluationService 只读 Interview/Question/Answer 数据，不反向调用其他 Service。

---

## 6. Data Model (refined from requirements.md Section 6)

```python
# SQLAlchemy models (simplified pseudo-schema)

class Interview:
    id: str (UUID)
    user_id: str | None  # MVP: NULL
    company_name: str
    company_style_id: str | None  # FK
    role_title: str
    language: str  # "zh" | "en"
    duration_min: int
    question_count_target: int
    mode: str  # MVP: "strict"
    status: str  # "in_progress" | "completed" | "abandoned" | "evaluation_failed"
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime
    resume_context: str | None  # 面试前临时存，结束后清空

class Question:
    id: str
    interview_id: str  # FK
    order_index: int
    question_text: str
    question_audio_s3_key: str | None
    generated_at: datetime

class Answer:
    id: str
    question_id: str  # FK
    user_audio_s3_key: str
    transcript_text: str
    answered_at: datetime
    duration_sec: float

class Evaluation:
    id: str
    interview_id: str  # FK
    question_id: str | None  # NULL → overall eval
    content_score: int  # 0-100
    expression_score: int
    voice_score: int
    overall_score: int
    improvement_suggestion: str
    ideal_answer: str | None  # 只在 question-level 有
    voice_features: dict (JSON)  # Transcribe + 轻补充
    rubric_version: str
    raw_prompt: str
    raw_response: dict (JSON)
    evaluation_cost: float  # USD
    generated_at: datetime

class CompanyStyle:
    id: str
    name: str
    interviewer_style_tags: list[str] (JSON)
    preferred_question_types: list[str] (JSON)
    sample_questions: list[str] (JSON)
    prompt_context_text: str
    is_builtin: bool
    created_by: str | None
    created_at: datetime
```

---

## 7. Key Architectural Decisions (ADR summary)

### ADR-001: WebSocket 放在 FastAPI 同进程而不是独立服务
- **Decision**: WS endpoint 和 REST endpoint 都在同一个 FastAPI 进程内
- **Rationale**: MVP 规模小（并发 ≤ 10），同进程减少运维复杂度
- **Trade-off**: 水平扩展受限（Beta 阶段可拆分 WS 为独立服务）

### ADR-002: Evaluation 异步执行用 asyncio.Task 而不是 SQS/Celery
- **Decision**: 面试完成后，InterviewService 创建 asyncio Task 执行 EvaluationService
- **Rationale**: MVP 单容器 + 并发小，asyncio 足够；避免引入 SQS/Redis
- **Trade-off**: 容器重启会丢失未完成的评估任务 → 通过"重试"按钮（US-017 AC）手动触发恢复

### ADR-003: 所有音频先落 S3 再给下游消费
- **Decision**: Nova Sonic 返回的音频片段，由后端实时写 S3 + 同时转发给浏览器
- **Rationale**: 音频持久化是 MVP 核心需求；写 S3 耗时可并行于转发
- **Trade-off**: 存储成本 + 延迟轻微增加（可忽略）

### ADR-004: Frontend 薄 BFF，业务在 FastAPI
- **Decision**: Next.js Route Handlers 只做代理，不放业务逻辑
- **Rationale**: 保持后端单一真相源；Python 生态对 Bedrock 支持最好
- **Trade-off**: 增加一次网络跳转（BFF → FastAPI）→ 可接受（内网延迟 < 10ms）


### ADR-005: 采纳 Strands Agents BidiAgent 作为 Nova Sonic 集成层
- **Decision**: 用 `strands-agents[bidi-all]` 的 `BidiAgent` + `BidiNovaSonicModel` 替代直接 boto3 双向流
- **Rationale**: Pre-POC（2026-04-26）验证 Strands SDK 封装好音频管线、事件协议、tools 机制；unit-2 复杂度从 L 降到 M
- **Alternatives**: (1) boto3 直连 — 3-5x 代码量；(2) AgentCore Runtime — 锁定云，与本地 Docker 决策冲突
- **Trade-off**: 优先开发速度；代价是依赖 `strands.experimental.*`，API 可能 breaking change → 缓释：pin 版本 + adapter 层（unit-2 的 `InterviewAgent` 包住 BidiAgent）

### ADR-006: MVP 部署目标为本地 Docker，不采用 AgentCore Runtime
- **Decision**: FastAPI + Strands BidiAgent 运行在本地 Docker 容器（macOS），通过本地浏览器访问
- **Rationale**: MVP 单用户自用场景，本地运行成本 $0（仅 Bedrock 按量付费），省 ~$50/月运行成本
- **Alternatives**: AWS App Runner / ECS Fargate — 留到 Beta 阶段引入真实用户后再评估
- **Trade-off**: 失去云原生扩展性；获得零运维、零 idle 成本、迭代速度
