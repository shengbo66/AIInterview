# unit-2 Code Generation Plan

**Unit**: unit-2 interview-engine
**Scope**: FastAPI WebSocket `/ws/interview/{id}` + 面试状态机 + Nova Sonic BidiAgent + 动态问题生成 + 音频持久化 + 成本计量
**Non-goals**: 评估（unit-3）、probe-on-weak（Phase-2）、前端（unit-4）
**依据**: `aidlc-docs/construction/unit-2-interview-engine/functional-design/unit-2-design.md`

---

## 1. Directory Layout（增量）

```
backend/
├── pyproject.toml                 # 新增依赖：strands-agents[bidi-all]
├── app/
│   ├── config.py                  # 新增 6 个 bidi_* 配置项
│   ├── clients/
│   │   └── nova_sonic.py          # NEW — Strands BidiAgent 封装
│   ├── services/
│   │   ├── question_service.py    # NEW — Claude 生成 Q1 / Qn+1
│   │   ├── bidi_session_recorder.py  # NEW — 音频 buffer + 持久化辅助
│   │   └── interview_engine_service.py  # NEW — 状态机核心
│   ├── routers/
│   │   └── bidi.py                # NEW — WS handler
│   └── main.py                    # 注册 bidi router + active_sessions set
└── tests/
    ├── test_question_service.py        # NEW
    ├── test_bidi_session_recorder.py   # NEW
    ├── test_interview_engine_contract.py  # NEW — WS 协议契约
    └── test_bidi_api_smoke.py          # NEW — ASGI + websockets 客户端驱动
```

**代码量预估**：~870 行（含测试）。

---

## 2. Tasks Checklist

### Part A: 配置 + 依赖
- [ ] A1. `pyproject.toml` 增加 `strands-agents[bidi-all]>=1.37,<2.0`
- [ ] A2. `config.py` 新增配置项：`nova_sonic_model_id / nova_sonic_voice / bidi_user_silent_timeout_sec / bidi_ws_heartbeat_sec / bidi_max_frame_bytes / bidi_max_answer_bytes / bidi_max_session_sec / question_default_target`
  - `bidi_max_answer_bytes: int = 10_485_760`（10 MB，~5 min 16kHz PCM16，Dev #3）
  - 不加 `public_ws_base_url`（Dev #1，前端自己拼 WS URL）
- [ ] A3. `.env.example` 更新默认值
- [ ] A4. `pip install -e ".[dev]"` 验证安装成功

### Part A0 (前置): Strands Usage Event Probe (Dev #4)
- [ ] A0. 扩展 `nova-sonic-poc/probe.py`:
  - 跑一次 ~30s 真实对话（启动 agent.py + probe 发送 silence PCM）
  - 打印所有 event type + payload 结构
  - 重点确认：(a) Strands 是否暴露 token usage；(b) input/output transcription 事件的确切名字
  - 产出：`nova-sonic-poc/strands-events.md` 一个短表（事件名 → 示例 payload）
  - 若 usage 不可用：在 config 加 `nova_sonic_price_per_sec: float = 0.0003`（Nova Sonic 约 $0.00018/sec 按 2026 定价，预留一点 buffer），按会话时长估算
  - **若该 probe 需要真 AWS 调用，由用户在本地运行并把输出贴给 AI**（避免 AI 代跑消费 AWS credits）

### Part B: NovaSonicClient
- [ ] B1. `app/clients/nova_sonic.py` — `NovaSonicClient` 类：
  - `@asynccontextmanager async def session(system_prompt: str) -> AsyncIterator[BidiAgent]`
  - 内部构造 `BidiNovaSonicModel`（参照 nova-sonic-poc/agent.py）
  - `last_usage()` 返回 `{input_tokens, output_tokens, cost_usd}`（从 agent 退出时的 usage event 汇总；若 Strands 未暴露则返回 0 并记 TODO）
  - 3x retry 在 session 进入失败时（setup_failed 场景）
- [ ] B2. 单元测试 `test_nova_sonic_client.py`: mock `BidiAgent` 验证 session 生命周期 + retry 逻辑（不调真 AWS）

### Part C: QuestionService
- [ ] C1. `app/services/question_service.py`:
  - `async def generate_first(interview, company_style) -> Question`:
    - 构造 Claude prompt = CompanyStyle.prompt_context_text + role_title + resume_context（若有）+ "生成第一题：结构化开场题，200 字内"
    - 复用 `app.clients.bedrock_claude.invoke_text`
    - 持久化 Question(order_index=0)，返回对象
  - `async def generate_next(interview, company_style, history: list[tuple[Question, Answer]]) -> Question`:
    - prompt 包含前 N 题的 Q + A transcript，要求"在已覆盖维度基础上递进或切换新维度，避免重复"
    - 持久化 Question(order_index=N)
- [ ] C2. 测试：mock `invoke_text`，覆盖 happy path + Claude 失败 3x 抛 RuntimeError（由 engine 吞下做降级）

### Part D: BidiSessionRecorder
- [ ] D1. `app/services/bidi_session_recorder.py`:
  - 纯内存状态管理器（不持有 DB session），接口如设计 §7.4
  - `start_ai_turn / append_ai_audio / end_ai_turn() -> bytes`
  - `start_user_turn / append_user_audio / end_user_turn() -> (bytes, float duration_sec)`
  - `append_*` 校验累计字节数 ≤ 上限（`bidi_max_frame_bytes * 2000`，约 60s 16kHz）防 OOM
- [ ] D2. 测试：单元覆盖所有方法 + 超限断言 + duration 计算

### Part E: InterviewEngineService（核心）
- [ ] E1. `app/services/interview_engine_service.py`:
  - `SessionState` Enum（SETUP/SPEAKING/LISTENING/PERSISTING/NEXT_Q/COMPLETED/ABANDONED）
  - `class InterviewEngineService` 构造接受 `websocket, interview_id, db_session_factory`
  - **DB session 约定**（Dev #5）：所有 service 方法接收 `db: AsyncSession` 参数；engine 在每个持久化节点用 `async with session_factory() as db:` 短事务；不跨事件循环持有 session
  - `async def run_session()` — 主循环：
    - SETUP: load Interview + CompanyStyle + Question.generate_first，置 `bidi_started_at`，发 `session_ready` + `question_start`
    - 进入 BidiAgent session context
    - 事件循环：并发 `asyncio.gather`(`_from_client()`, `_from_agent()`)
    - 状态迁移按 §4.1 状态机实现
    - 终态：更新 `status / bidi_ended_at / bidi_tokens_total / bidi_cost_usd`；清空 `resume_context`
  - 关键子方法：
    - `_handle_start_msg` / `_handle_audio_input` (校验 base64 + size)
    - `_on_ai_turn_end(question_id, order)` → upload + update question.s3_key
    - `_on_user_turn_end(question_id, order)` → upload + persist Answer
    - `_try_next_question()` → Claude，失败 3x → `completed_degraded` 或 `abandoned`（按 BR-3 阈值）
    - `_check_end_conditions()` → 按 BR-2 双限制
  - LISTENING 静默 timer：用 `asyncio.wait_for` + 状态切换时 cancel
  - **WS heartbeat: MVP 不实现**（Tester #3），依赖 TCP keepalive 和 WS disconnect 事件；Phase-2 再加
- [ ] E2. 全程无 `print`；用 Python `logging` 模块
- [ ] E3. 错误分类 helper：`_abandoned(reason)` / `_complete(degraded=False)` 统一清理路径

### Part F: WS Router + main.py 集成
- [ ] F1. `app/routers/bidi.py`:
  - 模块顶定义 `_active_sessions: set[str] = set()` + `_active_lock = asyncio.Lock()`（Dev #2）
  - `@router.websocket("/ws/interview/{interview_id}")`
  - 校验 interview 存在（SETUP 前做 100ms retry）
  - 进入前 `async with _active_lock:` 内 check-and-add；若已在 set → `await ws.close(4002)` 立即返回
  - 委托给 `InterviewEngineService(...).run_session()`
  - `finally` 块内 `async with _active_lock:` 做 discard
- [ ] F2. `app/main.py`: include bidi router
- [ ] F3. **保持 unit-1 的 `POST /api/interviews` response 不变**（Dev #1）:
  - **不改** `InterviewDetail` shape，**不新增** endpoint
  - `ws_url` 由前端按约定拼接：`ws(s)://{host}/ws/interview/{id}`
  - 若后续前端需要一次性拿到 ws_url，Phase-2 再做；本 unit 无该改动

### Part G: 测试
- [ ] G0. `tests/fixtures/fake_bidi_agent.py`（Tester #4）:
  - `BidiEvent` dataclass + `FakeBidiAgent` 类
  - `run(inputs, outputs, invocation_state)` 消费 inputs 并按预设脚本 yield 事件
  - 事件名以 Step A0 probe 结果为准（probe 未做前用占位 + TODO）
  - 被 G3/G4 共用
- [ ] G1. `test_nova_sonic_client.py`（从 Part B2 合并到 G，Dev #6）:
  - mock `BidiAgent` 构造 + `run` 调用
  - session 进入失败 3x retry → RuntimeError
- [ ] G2. `test_question_service.py` — mock `invoke_text`：
  - Q1 生成 happy path（order_index=0，prompt 含 company_style + role）
  - Q1 prompt 含 resume_context（若非空）
  - Qn+1 prompt 含历史 Q/A transcript
  - Claude 失败 3x 抛 RuntimeError
- [ ] G3. `test_bidi_session_recorder.py`:
  - AI/User turn buffer + end 返回完整 bytes
  - duration_sec 计算
  - `bidi_max_answer_bytes` 超限抛 ValueError（Dev #3）
- [ ] G4. `test_interview_engine_contract.py`（**协议契约**）:
  - 用 FakeBidiAgent 注入
  - Mock QuestionService + s3_audio
  - 断言正向序列：session_ready → question_start(0) → bidi_audio_stream*N → ai_speaking_end → user_transcript_partial* → user_transcript_final(0) → question_start(1) → ... → interview_complete
  - 断言 §5.4 不变式（每个 question_start 后恰好一次 user_transcript_final）
  - 断言 start 幂等（发 2 次只触发 1 次 SETUP）
  - 断言 `session_ready` 之前只能收到 `error`（SETUP 失败时）（Tester #5）
- [ ] G5. `test_bidi_api_smoke.py`（Tester #1 技术栈）:
  - **使用 `fastapi.testclient.TestClient`**（同步，支持 `client.websocket_connect()`），非 httpx.AsyncClient
  - 注入 FakeBidiAgent via dependency override
  - POST create interview → 用其 id 连接 `/ws/interview/{id}`
  - 驱动完整流程，断言最终 `interview.status == "completed"`
- [ ] G6. 降级路径测试（并入 `test_bidi_api_smoke.py` 或独立 `test_bidi_failures.py`）:
  - Claude Qn+1 失败 3x 且 N >= target/2 → `completed_degraded`
  - **Claude Qn+1 失败 3x 且 N < target/2 → `abandoned`**（Tester #2）
  - SETUP 时 Sonic 建立失败 → close 4003，确保 close 前仅发送 `error` 而非 `session_ready`
  - 重复连接同一 interview_id → close 4002
  - 单帧超限（> `bidi_max_frame_bytes`）→ close 1009
  - 静默超时在 LISTENING 触发；SPEAKING 中不触发（计时器 pause）
  - `bidi_max_session_sec=2` 强制硬截断（Tester #6）

### Part H: 验证
- [ ] H1. `pytest backend/tests/ -q` 全绿（unit-1 24 测试 + unit-2 新增 ~20 测试）
- [ ] H2. `ruff check backend/` pass
- [ ] H3. 本地启服务 `uvicorn app.main:app`，curl `/api/health` + 手动 WS 连接（不调真 Sonic，仅测协议落地）
- [ ] H4. 更新 `aidlc-state.md`：unit-2 complete

### Part I: 延后项（不在本次交付，但需记录）
- [ ] I1. **smoke_bidi.py 真实 Sonic 集成测试** —— 不进 CI，写清运行成本提示，延后到 unit-4 前端联调时再跑
- [ ] I2. **ADR-007 Strands BidiAgent 选型** —— 补一条 ADR（已在 unit-2-design §2 决策表提及，但未单独落 ADR 文件），可纳入下次 AIDLC cycle

---

## 3. Key Design Decisions (实施层)

| 决策 | 选择 | 理由 |
|---|---|---|
| Strands 版本 | `strands-agents[bidi-all]>=1.37,<2.0` | pre-POC 已验证；锁定 major 防 breaking |
| DB session 注入 | engine 接受 `session_factory: async_sessionmaker`，按需 `async with` | 长会话不宜复用单个 session（SQLite WAL 锁问题） |
| Logging | `logging.getLogger("interviewer.bidi")` | 生产可配级别；测试可用 caplog |
| Mock 策略 | Nova Sonic / Claude / S3 全 mock；不跑真 AWS | 与 unit-1 一致 |
| Timer 实现 | `asyncio.wait_for(receive, timeout=60)` 仅在 LISTENING 分支；state 切换时替换 awaitable | 简单，无需独立 task |
| active_sessions 存储 | `set[str]` 模块级 singleton + `asyncio.Lock` | MVP 单实例；§14 已标注多实例限制 |
| WS URL scheme 推导 | `request.url.scheme == "https" → "wss"`；fallback `ws` | 最少代码 |

---

## 4. Execution Order（7 步）

| Step | Parts | 目标 | 预估时长 |
|---|---|---|---|
| 0 | A0 | Strands usage event probe（可能需用户本地跑） | 30 分钟 |
| 1 | A | 依赖 + config + env | 30 分钟 |
| 2 | B + C + D | 三个底层模块独立可测 | 2 小时 |
| 3 | E | 状态机实现 | 3 小时（最难） |
| 4 | F | WS router + main.py 注册 | 30 分钟 |
| 5 | G | 测试 | 2 小时 |
| 6 | H + 更新 state.md | 验证 + 收尾 | 30 分钟 |

每步结束 `pytest + ruff check` 必须通过才推进。

---

## 5. Risks & Mitigations (实施层)

| 风险 | 缓解 |
|---|---|
| Strands BidiAgent 的事件类型与文档不符 | Step 2 里 NovaSonicClient 加一个 "unknown event" 日志兜底；若 contract test 失败则扩展 probe.py 实际抓事件 |
| 状态机测试难以确定性驱动 | 用假 agent（Python `AsyncMock` 可 `aiter` 产出脚本化事件序列）；不依赖 real BidiAgent 的 event loop |
| `request.base_url` 在 ASGITransport 测试里可能是 `http://test/` | 测试里先验证 ws_url 生成逻辑，smoke 测试直接用 `ws://test/ws/...` 连接（httpx 不支持 WS，改用 `websockets` 驱动 ASGI lifespan） |
| 长会话导致 SQLite 并发锁 | 每次 DB 写入短事务；engine 主循环不持有 session |

---

## 6. Approval

回复 `approve` 按以上计划开始 Step 1；或指出要调整的项。
