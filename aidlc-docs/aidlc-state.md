# AI-DLC State Tracking

## Project Information
- **Project Name**: Interviewer (Mock Interview Platform)
- **Project Type**: Greenfield
- **Start Date**: 2026-04-25T21:14:51+08:00
- **Last Session End**: 2026-04-30T23:47:00+08:00
- **Current Stage**: **Sprint 3 COMPLETE ✅ → 待浏览器验证评估展示效果**

## Workflow Note
正式 AIDLC unit-by-unit 流程（unit-1..unit-5）在 2026-04-28 与 PM review 之后**转向 Agile Sprint 模式**（walking skeleton → 增量迭代），理由：用户 3 天未接触产品，需要立即建立反馈闭环。原 AIDLC 设计文档（requirements, unit-of-work, unit-2-design）作为"北极星"保留，但执行按 Sprint 推进。

---

## Sprint Timeline

### 🔵 INCEPTION — ALL COMPLETE ✅ (2026-04-25)
- Workspace Detection / Requirements v1.2 / User Stories v1.1 / Workflow Planning / Application Design (ADR-001..006) / Units Generation

### 🟢 CONSTRUCTION

**unit-0 POC** — ✅ PASSED en + zh (2026-04-26)

**unit-0.5 Strands Pre-POC** — ✅ PASSED (2026-04-26)
- Nova Sonic bidi session 本地可建立
- `nova-sonic-poc/agent.py` + `probe.py` + `probe_events.py`
- 产出 `strands-events.md` 锁住 Strands API shape

**unit-1 backend-core** — ✅ COMPLETE (2026-04-26)
- 24 测试 pass，ruff 绿，本地 smoke 通过
- FastAPI + async SQLAlchemy + Alembic + Huawei seed + REST endpoints

**unit-2 interview-engine Functional Design + Code Plan** — ✅ APPROVED (2026-04-26)

**Sprint 1 Walking Skeleton** — ✅ WORK (2026-04-29)
- 单页 Next.js + AudioWorklet + WS + Nova Sonic 端到端
- 用户第一次体验到产品

**Sprint 2 持久化 + UI Polish + 两个真 bug 修复** — ✅ COMPLETE (2026-04-29~30)
- 持久化：Interview/Question/Answer 落库 + usage 计量
- UI：AI 说话状态显示 + timestamp + level meter
- **故障排查 6 轮**才定位真因：**Nova Sonic 永不主动开口，必须 hello.pcm bootstrap**
- 修复方案：`backend/assets/hello.pcm` (macOS `say`+ffmpeg 生成) → demo_bidi.py 的 recv() 先 yield hello chunks 再读 WS
- 真实浏览器测试暴露第二批 bug（2026-04-30 后半段）：
  - Answer UNIQUE constraint：user transcript 多段 is_final 被 insert 多次 → fix: UPSERT 合并
  - ws.send_json 失败 raise 把 Strands restart 杀掉 → fix: swallow WS failure
- 独立验证：`scripts/ws_smoke.py` 证明 backend pipeline 100% work
- 真实 12 分钟 45 轮浏览器面试顺畅完成（interview b34b3f9d）
- 自动化测试：24 → **60**（+150%），54 pytest + 6 vitest，全绿

**Sprint 3** — ✅ COMPLETE (2026-04-30)
- S2-3 历史列表页 `/history` + 详情页 `/history/[id]`（Q/A timeline + 评估展示）
- S2-4 评估 pipeline：`evaluation_service.py` stage1 (per-Q Claude) + stage2 (overall Claude)
- 自动触发：finalize 后 fire-and-forget background task
- 手动重试：`POST /api/interviews/{id}/evaluate`
- 状态机：completed → evaluating → evaluated | evaluation_failed | evaluation_skipped
- 真实验证：12 分钟 13 Q/A 面试成功评估（14 evals, ~3 min Claude 处理）
- 自动化测试：54 pytest + 6 vitest = **60 测试全绿**（+3 evaluation tests）
- Sprint 3 scope: voice_score = 0（音频分析留 Sprint 4）

**Sprint 4** — NOT STARTED
- 浏览器验证 Sprint 3 评估展示效果
- 音频回放（S3 presigned URL）
- voice_features 分析
- Prompt 优化（面试节奏）
- UI polish

---

## 🔥 核心技术决策 (Sprint 2 积累)

### Nova Sonic "hello.pcm" Bootstrap（最关键）
**Sonic 永远不主动开口** — 必须用"用户假装先打招呼"触发。否则 55s 内发 `ValidationException: Timed out waiting for audio bytes`。参考 `sample-amazon-nova-sonic-twilio-integration` 官方示例相同做法。

### turn_detection 必配
V2 模型 (`amazon.nova-2-sonic-v1:0`) 需显式配置：
```python
"turn_detection": {"endpointingSensitivity": "MEDIUM"}
```

### 并发模型
- `asyncio.Lock` 串行化所有 DB 写（SQLite 不支持并发写）
- S3 upload 是 background task，不阻塞 Strands 事件循环
- `BidiInterviewSession._background_tasks` set；finalize 时 drain

### 前端 WS 时序
- AudioWorklet `source.connect(node)` 必须等 WS onopen 后
- `aiSpeakingRef` 在 AI 说话时 mute mic，防止自打断

---

## 📂 Directory Layout (current)

```
interviewer/
├── shared/eval_core/           # 纯逻辑 pkg (28 tests)
├── poc/                        # Phase 0 POC (✅ PASSED)
├── nova-sonic-poc/             # Pre-POC + strands-events.md probe report
│
├── backend/                    # FastAPI (52 tests ✅)
│   ├── app/
│   │   ├── main.py             # + lifespan seed + CORS + logging
│   │   ├── routers/demo_bidi.py  # WS /ws/interview-demo + hello.pcm bootstrap
│   │   ├── services/bidi_interview_session.py  # 持久化 + turn 管理
│   │   ├── logging_config.py   # logs → /tmp/interviewer-backend.log
│   │   └── ... (health, interviews, company_styles, audio 等 routers)
│   ├── assets/hello.pcm        # ❗ bootstrap greeting (0.54s, 16kHz PCM16)
│   ├── scripts/ws_smoke.py     # 独立 smoke test（可跑真 AWS）
│   └── tests/                  # 52 pytest
│
├── frontend/                   # Next.js 15 (6 vitest ✅)
│   ├── app/page.tsx            # 单页 UI
│   ├── public/pcm-worklet.js   # 浏览器 PCM 采集
│   ├── lib/audio-codec.ts      # base64↔PCM (6 vitest)
│   └── vitest.config.ts
│
└── aidlc-docs/
    ├── aidlc-state.md          # 本文
    ├── audit.md                # 交互时间线
    ├── inception/              # requirements, stories, ADRs
    └── construction/
        ├── unit-1-backend-core/
        ├── unit-2-interview-engine/functional-design/
        ├── plans/
        └── phase0-poc/
```

---

## 🧪 测试现状 (58 测试全绿)

### Backend `pytest -q` (9s)
- 原有 42 个 (unit-1 的 24 + bidi session 的 18)
- 新增 10 个（Sprint 2 trouble shooting 结论）：
  - `test_bootstrap_hello_injected_before_ws_audio` — 🔒 锁住 hello.pcm 不被回归
  - `test_bootstrap_triggers_session_without_client_audio` — 端到端零用户输入
  - `test_client_disconnects_midway_interview_finalized`
  - `test_agent_run_raises_still_finalizes`
  - `test_ws_send_failure_does_not_deadlock`
  - `test_turn_buffer_*` (4 个 unit tests)
  - `test_interruption_does_not_leak_ai_audio` — **修复真 bug**：session 原本不识别 bidi_interruption

### Frontend `npm run test` (200ms)
- 6 个 Vitest：base64 round-trip / empty / 100ms chunk / 64KB 跨 chunk 边界 / 奇数字节 / base64 合法性

### 独立验证工具
`backend/scripts/ws_smoke.py` — Python WS 客户端，可发合成音频或真实 PCM 文件。`SMOKE_REAL_AWS=1` 打真 Sonic（~$0.01/次）。

---

## 🚦 下次会话起点

### Resume Instructions
```bash
# Backend
cd /Users/shengbo/dev/interviewer/backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend
cd /Users/shengbo/dev/interviewer/frontend && npm run dev

# Smoke test (independent backend verification)
python backend/scripts/ws_smoke.py --tone 0    # 不发用户音频，验证 hello.pcm 触发
```

### 下次第一句话应该是
- **"浏览器试了，xxx"** → 验证 Sprint 2 hello.pcm 修复在真实浏览器下是否 work
- **"继续 S2-3"** → 跳过手测，先做历史页 + 详情页

---

## 已知坑（别再踩）

1. **Sonic 不主动开口** — 永远别假设它会；必须 hello bootstrap
2. **别猜 bug 根因** — 4 轮猜错经验（AudioContext resume / worklet timing / asyncio Lock / Event pattern），最后是 hello.pcm。**加 smoke script + 集成测试**定位真因
3. **SQLite in-memory 测试必须 StaticPool + check_same_thread=False**
4. **SQLite 单连接不支持并发写** — `asyncio.Lock` 串行化
5. **DB lock 里别做 S3 upload**（会卡所有写）
6. **Strands experimental API** — 锁 `strands-agents[bidi-all]>=1.37,<2.0`
7. **recv() 里不 raise WebSocketDisconnect** 会让 agent.run 正常退出

---

## Key Documents
| Doc | Path |
|---|---|
| Requirements v1.2 | aidlc-docs/inception/requirements/requirements.md |
| Application Design + ADRs | aidlc-docs/inception/application-design/components.md |
| unit-2 Design | aidlc-docs/construction/unit-2-interview-engine/functional-design/unit-2-design.md |
| unit-2 Code Plan | aidlc-docs/construction/plans/unit-2-code-generation-plan.md |
| Strands Event Schema | nova-sonic-poc/strands-events.md |
| POC Verdict | aidlc-docs/construction/phase0-poc/poc-verdict.md |
| Audit Trail | aidlc-docs/audit.md |
