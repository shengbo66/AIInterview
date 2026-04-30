# Units of Work — Mock Interview Platform

**Date**: 2026-04-25
**Scope**: Phase 0 POC + Phase 1 MVP (6 units total)

---

## Unit List

### Unit 0: `poc-evaluation-algorithm` (Phase 0)

**Goal**: 验证 Transcribe Call Analytics + Claude Sonnet 评估算法可行性（Gate 通过前不进 MVP）

**Stories**: US-000
**Deliverables**:
- `poc/` 目录下的 Python 命令行脚本
- `aidlc-docs/construction/phase0-poc/` 下的 rubric、样本、结果、verdict

**Components involved**: (无生产组件，独立脚本)
**Tech**: Python 3.12, boto3, anthropic-bedrock, Polly (TTS)
**Size**: S (Small, 2-3 天)
**Depends on**: —
**Blocks**: unit-1 ~ unit-5（Gate 未过不进 MVP）

---

### Unit 1: `backend-core` (Phase 1 MVP)

**Goal**: FastAPI 骨架 + DB schema + Bedrock 接入层 + S3 + 基础 REST APIs

**Stories**: 基础设施（无直接 story，支撑 US-010/011/014 的记录查询/删除）

**Components**:
- FastAPI app skeleton + health endpoint
- SQLAlchemy 2.0 async + Alembic + SQLite WAL
- StorageAdapter
- BedrockClient（封装 Nova Sonic + Claude invoke）
- AudioService + S3 client + pre-signed URL
- CompanyStyleService + 内置风格 seed 数据
- RecordService (CRUD) + 部分 REST endpoints:
  - GET /api/health
  - GET /api/company-styles, POST /api/company-styles/upload
  - GET /api/interviews (list), GET /api/interviews/{id}, DELETE /api/interviews/{id}
  - GET /api/interviews/{id}/audio/{segment_idx} (pre-signed URL)

**Tech**: FastAPI, SQLAlchemy 2.0, Alembic, boto3, python-multipart
**Size**: M (3-4 天)
**Depends on**: unit-0 (POC Gate passed)
**Blocks**: unit-2, unit-3, unit-4, unit-5

---

### Unit 2: `interview-engine` (Phase 1 MVP)

**Goal**: 面试生命周期管理 + Nova Sonic WebSocket 双向流编排 + 动态问题生成

**Stories**: US-004, US-005, US-006 (backend 部分), US-007, US-008

**Components**:
- WS Gateway `/ws/interview/{id}`
- InterviewService (create/start/complete/abandon)
- QuestionService (调用 Claude 生成下一题)
- 音频格式转换 (WebM/Opus → LPCM 16kHz via ffmpeg-python)
- POST /api/interviews (创建面试，返回 id + ws_url)

**Tech**: FastAPI WebSocket, ffmpeg-python, Nova Sonic bidirectional stream
**Size**: L (4-5 天) — 最复杂的 unit
**Depends on**: unit-1
**Blocks**: unit-3 (evaluation 依赖面试完成事件)

---

### Unit 3: `evaluation-pipeline` (Phase 1 MVP)

**Goal**: 评估引擎（集成 POC 产出的算法到生产后端）

**Stories**: US-015, US-016, US-017

**Components**:
- EvaluationService (基于 POC rubric + prompt 迭代)
- TranscribeClient (Call Analytics 调用)
- BackgroundWorker (asyncio.Task 异步触发)
- POST /api/interviews/{id}/evaluation/retry
- GET /api/interviews/{id}/evaluation

**Tech**: 复用 POC 代码、Transcribe Call Analytics, Claude Sonnet
**Size**: M (2-3 天) — 因 POC 已铺路
**Depends on**: unit-0 (算法), unit-1 (DB/Bedrock), unit-2 (面试完成事件)
**Blocks**: unit-5 (详情页需要评估数据)

---

### Unit 4: `frontend-interview` (Phase 1 MVP)

**Goal**: Next.js 设置页 + 面试页 + 等待页

**Stories**: US-001, US-002, US-003, US-004, US-006, US-007, US-009, US-017 (前端部分)

**Components**:
- SetupPage (shadcn/ui Form)
- InterviewPage (音波 Framer Motion + WebSocket + MediaRecorder)
- WaitingPage (轮询评估状态)
- AudioCapture hook
- WebSocketClient hook
- ApiClient (openapi-typescript 自动生成)
- Error states for FR-6.1/6.2/6.3

**Tech**: Next.js 15, React 19, Tailwind, shadcn/ui, Framer Motion, Vercel AI SDK (optional)
**Size**: L (4-5 天)
**Depends on**: unit-1 (API), unit-2 (WS endpoint)
**Blocks**: —

---

### Unit 5: `frontend-history` (Phase 1 MVP)

**Goal**: Next.js 记录列表 + 详情页 + 音频回放

**Stories**: US-010, US-011, US-013 (音频下载 - Should), US-014 (删除 - Should)

**Components**:
- HistoryListPage (卡片网格 + 分页)
- InterviewDetailPage (雷达图 + 每题分析 + 音频播放器)
- 按段落点击播放逻辑
- 评分动画（Framer Motion + recharts/tremor）

**Tech**: Next.js 15, shadcn/ui, Framer Motion, recharts（雷达图）
**Size**: M (2-3 天)
**Depends on**: unit-1 (API), unit-3 (评估数据)
**Blocks**: —

---

## Dependency Graph

```
            ┌─────────────────┐
            │ unit-0 POC      │
            │ (Gate)          │
            └────────┬────────┘
                     │ PASS
                     ▼
            ┌─────────────────┐
            │ unit-1 backend  │
            │ core            │
            └────┬────────┬───┘
                 │        │
         ┌───────▼┐    ┌──▼──────────────┐
         │unit-2  │    │ unit-4 frontend │
         │engine  │    │ interview       │
         └───┬────┘    └─────────────────┘
             │
         ┌───▼─────────┐
         │ unit-3 eval │
         └───┬─────────┘
             │
         ┌───▼──────────────┐
         │ unit-5 frontend  │
         │ history          │
         └──────────────────┘
```

**Critical Path**: unit-0 → unit-1 → unit-2 → unit-3 → unit-5
**Parallelism**: unit-2 与 unit-4 可并行（两者都只依赖 unit-1）

---

## Unit ↔ Story Map

| Story | Primary Unit | Secondary Unit |
|---|---|---|
| US-000 | unit-0 | — |
| US-001 (配置面试参数) | unit-4 | unit-1 (API) |
| US-002 (选内置公司) | unit-4 | unit-1 |
| US-003 (上传自定义风格) | unit-4 | unit-1 |
| US-004 (上传简历) | unit-4 | unit-2 |
| US-005 (语音面试) | unit-4 | unit-2 |
| US-006 (面试中进度) | unit-4 | unit-2 |
| US-007 (严格模式) | unit-4 | unit-2 |
| US-008 (动态问题) | unit-2 | — |
| US-009 (错误场景) | unit-4 | unit-1, unit-2 |
| US-010 (记录列表) | unit-5 | unit-1 |
| US-011 (详情回放) | unit-5 | unit-1, unit-3 |
| US-012 (导出 PDF - Should) | unit-1 | unit-5 |
| US-013 (下载音频 - Should) | unit-5 | unit-1 |
| US-014 (删除 - Should) | unit-5 | unit-1 |
| US-015 (三维评分) | unit-3 | unit-5 |
| US-016 (每题建议) | unit-3 | unit-5 |
| US-017 (评估等待体验) | unit-4 | unit-3 |

---

## Execution Sequence Summary

```
Week 1:       unit-0 POC (2-3 天，Gate)
Week 1-2:     unit-1 backend core (3-4 天)
Week 2-3:     unit-2 interview engine || unit-4 frontend interview (并行 4-5 天)
Week 3-4:     unit-3 evaluation pipeline (2-3 天)
Week 4:       unit-5 frontend history (2-3 天)
Week 4-5:     Build & Test（集成）
```

**总计**：~4-5 周（含并行和 Build & Test）

---

## Critical Success Factors

1. **unit-0 POC 必须 PASS** — 算法不通过 MVP 整体 revise
2. **API 契约稳定** — unit-1 完成后 OpenAPI spec 冻结，前后端基于 spec 独立开发
3. **unit-2 是技术风险最高** — Nova Sonic 双向流集成 + 音频转码
4. **unit-3 复用 POC 代码** — 避免重复实现评估逻辑
