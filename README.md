# Interviewer

AI 语音面试平台 — **华为 · 硬件技术工程师（射频技术方向）实习生**  
基于 Amazon Nova Sonic 双向语音流 + Claude 文本评估。

## 架构

```
 Browser (Next.js 15)                FastAPI (Python 3.12)            AWS Bedrock
 ┌─────────────────┐                ┌────────────────────┐          ┌────────────┐
 │ AudioWorklet    │  PCM16 16kHz   │ /ws/interview-demo │  bidi    │Nova Sonic  │
 │ MediaDevices    │ ◄─────────────►│ (Strands BidiAgent)│ ◄───────►│   (V2)     │
 │ WebSocket       │  base64 JSON   │                    │          └────────────┘
 │ Tailwind UI     │                │ BidiInterviewSession│
 └─────────────────┘                │ (persistence)       │          ┌────────────┐
                                    └──────────┬─────────┘          │  Claude    │
                                               │                     │ (Sonnet)   │
                                     ┌─────────┼──────────┐          └────────────┘
                                     ▼         ▼          ▼
                                  SQLite     S3 Audio   Seed
                                  (WAL)                 (Huawei)
```

核心流程：浏览器采 PCM → WebSocket → Strands BidiAgent → Nova Sonic → 实时 AI 音频流回浏览器 + 转录 + 持久化 → 面试结束后 Claude 评估（Sprint 3）。

## 测试状态

| 层 | 测试数 | 命令 | 时长 |
|---|---|---|---|
| Backend | 52 pytest | `cd backend && pytest -q` | ~9s |
| Frontend | 6 vitest | `cd frontend && npm test` | ~200ms |
| Smoke | 独立 WS 脚本（真 AWS） | `python backend/scripts/ws_smoke.py --tone 0` | ~30s, ~$0.01 |

## 本地启动

### 前置
- Python 3.12 + [uv](https://github.com/astral-sh/uv) 或 venv
- Node.js 20+ / npm
- AWS credentials (`~/.aws/credentials`) 有访问 `us-east-1` Bedrock + S3 权限

### 起服（两个终端）

```bash
# 终端 1 — Backend
cd backend
source .venv/bin/activate       # 首次: uv venv && pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# 终端 2 — Frontend
cd frontend
npm install                     # 首次
npm run dev                     # http://localhost:3000
```

浏览器打开 http://localhost:3000，点"开始面试"，允许麦克风。AI 会主动用中文开场 + 问第一题。

### 日志位置
Backend 日志写入 `/tmp/interviewer-backend.log`（滚动 10MB × 2 backup）。

## 测试

```bash
# Backend
cd backend
source .venv/bin/activate
ruff check app/ tests/          # lint
pytest -q                       # 52 tests

# Frontend
cd frontend
npx tsc --noEmit                # type check
npm test                        # 6 vitest

# End-to-end smoke (真 AWS，验证 backend pipeline)
cd backend
python scripts/ws_smoke.py --tone 0         # bootstrap-only mode
python scripts/ws_smoke.py --pcm-file /tmp/my-speech.pcm  # 用真人 PCM
```

## 项目结构

```
interviewer/
├── backend/                    # FastAPI
│   ├── app/
│   │   ├── main.py             # FastAPI app + lifespan + CORS
│   │   ├── routers/
│   │   │   ├── demo_bidi.py    # ❗ WS endpoint + Nova Sonic bootstrap
│   │   │   ├── health.py / interviews.py / audio.py / company_styles.py
│   │   ├── services/
│   │   │   ├── bidi_interview_session.py  # 持久化 + turn 管理
│   │   │   ├── record_service.py / audio_service.py / company_style_service.py
│   │   ├── clients/            # bedrock_claude.py, s3_audio.py
│   │   ├── models.py           # 5 tables: interview/question/answer/evaluation/company_style
│   │   ├── seed/               # Huawei + RF Intern seed
│   │   └── logging_config.py   # logs → /tmp/interviewer-backend.log
│   ├── assets/hello.pcm        # ❗ Sonic bootstrap greeting (必需)
│   ├── alembic/                # async migrations
│   ├── scripts/ws_smoke.py     # 独立 WS 测试客户端
│   └── tests/                  # 52 pytest
│
├── frontend/                   # Next.js 15 App Router + TypeScript + Tailwind
│   ├── app/
│   │   ├── page.tsx            # 单页 UI（Sprint 1+2 walking skeleton）
│   │   ├── layout.tsx / globals.css
│   ├── public/pcm-worklet.js   # AudioWorklet（浏览器 PCM 采集）
│   ├── lib/
│   │   ├── audio-codec.ts      # base64↔PCM16
│   │   └── audio-codec.test.ts # 6 vitest
│   └── vitest.config.ts
│
├── shared/eval_core/           # 跨后端/POC 共享的纯评估逻辑 (28 tests)
├── poc/                        # Phase 0 POC（评估算法验证）
├── nova-sonic-poc/             # Strands BidiAgent Pre-POC + probe 产出
│   ├── agent.py / probe.py / probe_events.py
│   └── strands-events.md       # Nova Sonic 事件 schema 参考
│
└── aidlc-docs/                 # AIDLC 工作流文档
    ├── aidlc-state.md          # 当前状态 + resume 指南
    ├── audit.md                # 交互时间线
    ├── inception/              # requirements, stories, ADRs
    └── construction/           # unit designs, code plans, phase0 POC
```

## ❗ 关键坑（参考 `aidlc-docs/aidlc-state.md`）

1. **Nova Sonic 永不主动开口** — 必须注入 `backend/assets/hello.pcm` 假装用户先说话
2. **必须配置 `turn_detection`** — V2 模型需要显式开启才能做 VAD
3. **SQLite 测试用 `StaticPool`** — 否则每次 checkout 独立 DB
4. **DB lock 范围** — 别把 S3 upload 包进 DB lock
5. **Strands API** — 锁 `strands-agents[bidi-all]>=1.37,<2.0`

## 开发工作流

本项目基于 **AIDLC**（AI Development Life Cycle，详见 `aidlc-docs/`）+ **Agile Sprint** 混合模式。  
Sprint 推进：每个 sprint 交付可体验的增量，所有代码改动有自动化测试覆盖。

### 参考
- [AIDLC rules](~/.kiro/steering/aws-aidlc-rules/)
- [Team Review matrix (Section 12)](aidlc-docs/...)
- Nova Sonic 生产参考：
  - https://github.com/aws-samples/sample-amazon-nova-sonic-twilio-integration
  - https://github.com/aws-samples/sample-sonic-contact-center-with-vonage

## License

Internal / WIP — 尚未公开发布。
