# unit-2 interview-engine — Functional Design

**Scope**: WebSocket 面试编排 + Nova Sonic bidi 会话 + 动态问题生成 + 音频持久化 + 成本计量
**Non-goals**:
- 评估执行（unit-3）
- 追问弱答案（probe-on-weak，**Phase-2 延后**，见 §11）
- 前端 MediaRecorder / AudioWorklet（unit-4）
- 生产部署 ECS 配置（unit-1 已有 Docker；运维阶段）

---

## 1. Delivered Components

### 1.1 WebSocket Endpoint

| Path | 作用 | Unit |
|---|---|---|
| `WS /ws/interview/{interview_id}` | 面试音频双向流 + 事件协议 | unit-2 |

### 1.2 REST Endpoint（unit-2 新增）

| Method | Path | 作用 | Response |
|---|---|---|---|
| POST | `/api/interviews` | 覆盖 unit-1 的占位实现：返回 `ws_url` 指向本 unit 的 WS 端点 | `{id, ws_url, status}` |

> unit-1 已实现 `POST /api/interviews` 创建 DB 记录；unit-2 只扩展 `ws_url` 生成逻辑（从 request base_url 推导 `ws://host/ws/interview/{id}`），不改 DB 层。

### 1.3 Services

- **InterviewEngineService** — 面试状态机 + Nova Sonic BidiAgent 生命周期
- **QuestionService** — 调用 Claude 生成单题（Q1 首题 + Qn+1 承接题）
- **BidiSessionRecorder** — 音频分段 + 事件捕获 + Interview.bidi_* 字段更新

### 1.4 Clients

- **NovaSonicClient** — Strands `BidiAgent` + `BidiNovaSonicModel` 封装（延续 nova-sonic-poc/agent.py 的形态）
- 复用 unit-1：`bedrock_claude.py`（QuestionService 调用）、`s3_audio.py`（音频上传）

---

## 2. 关键设计决策（本次锁定）

| # | 决策 | 选择 | 依据 |
|---|---|---|---|
| D1 | 流程控制归属 | **Strands `BidiAgent` 负责整场对话**（一个 agent = 整场面试） | ADR-005；nova-sonic-poc 已验证；最小化编排复杂度 |
| D2 | 问题生成时机 | **Q1 面试开始前生成；Qn+1 在 Qn 答完后生成** | US-008 动态；为未来 probe 留接口 |
| D3 | 答案结束检测 | **Hybrid**：Sonic 的 `inputTranscriptionCompleted` + end-of-turn 事件为主；客户端静默检测为兜底 | Sonic VAD 本就为此设计 |
| D4 | 音频上传策略 | **完整 answer 服务端 buffer → 单次 S3 上传** | 单答 < 5 MB，内存无压力；失败恢复简单 |
| D5 | 音频格式 | **浏览器 AudioWorklet 直接采集 PCM16 16kHz → server 透传 → Sonic LPCM 输出 → 客户端 WebAudio 播放** | 去掉 ffmpeg 依赖；匹配 POC `input_rate: 16000, format: pcm` |
| D6 | unit-2 scope | **C: WS + 状态机 + 动态问题 + 基础错误处理；probe-on-weak 延后** | 保 L 体量（3-4 天）；probe 作为 Phase-2 延伸，见 §11 |

**继承自 Application Design / ADR**：

| Decision | Choice | Source |
|---|---|---|
| Framework | FastAPI WebSocket | unit-1 |
| Bedrock 模型 | Nova Sonic `amazon.nova-2-sonic-v1:0` + Claude Sonnet 4.5 | ADR-005 |
| Voice | `tiffany`（可后续配置） | POC |
| Region | us-east-1 | Req §5.1 |
| 音频存储 | S3 bucket `interviewer-poc-audio-484626021127` | unit-1 |
| WS 认证 | 无（MVP 单用户） | Req |

---

## 3. 核心业务规则

**BR-1 面试生命周期**：
- 客户端 `POST /api/interviews` → DB 插入 `interview` 行（status=`in_progress`），得到 `{id, ws_url}`。
- 客户端连接 `ws_url`，发送 `{"type":"start"}` → 服务端进入 SETUP 状态。
- 面试结束或异常断连 → 服务端标记 `status` 并持久化累计 `bidi_*` 计量字段。

**BR-2 题量控制**：
- `question_count_target` 来自 Interview（默认 8）。
- 第 N 题答完后，若 N < target **且** 时长 < `duration_min` → 生成 N+1 题；否则触发结束流程。
- **双限制优先级**（Tester #1）：
  - `duration_min` 软截断：到时后允许**当前题答完**再 END，不强制打断 LISTENING / PERSISTING。
  - 若到时时仍在 SPEAKING（AI 刚开口）：立即跳至 END，该题不计入（已写 DB 的 Question 保留，Answer 为空；unit-3 评估时若 Question 无关联 Answer 则跳过该题）。
  - `question_count_target` 硬上限：答满 target 后立即 END，不看时长。

**BR-3 强制中止**：
- 客户端断连 → 标记 status=`abandoned`，已持久化的 Q/A 保留。
- 服务端错误（Sonic 建立失败 3 次）→ status=`abandoned`，记录 `abandon_reason`（DB 无此字段，写入 `resume_context` 兜底，unit-3 评估时跳过）。
- **降级完成**（Arch #2）：Claude Qn+1 生成失败 3x，面试以 `status="completed_degraded"` 结束。
  - 该枚举值新增到 `Interview.status` 取值（无需迁移 DB schema，字段已是 String(30)）。
  - 同时在 `resume_context` 写 `{"degraded_reason":"claude_qgen_failed","completed_at_question":N}`，供 unit-3 评估时感知。
  - 若 `N < question_count_target / 2`（题量不足一半）则改判 `abandoned` 而非 `completed_degraded`。

**BR-4 音频持久化粒度**：
- 每个 Question：**一条** AI 音频（提问 TTS） + **一条** User 音频（回答）。
- 命名规则：
  - 问题音频：`interviews/{id}/q{order_index}.pcm`
  - 回答音频：`interviews/{id}/a{order_index}.pcm`
- **上传时机**（Arch #1）：
  - AI 音频：SPEAKING → LISTENING 跳转时，`BidiSessionRecorder.end_ai_turn()` 返回完整 PCM → `s3_audio.upload` → 成功后 update `Question.question_audio_s3_key`。
  - User 音频：LISTENING → PERSISTING 跳转时，同样的 buffer → upload → update 模式。
- 写 S3 成功后再写 DB 对应字段，保证最终一致；失败则字段为 NULL（§8 错误矩阵已规定降级行为）。

**BR-5 成本计量**：
- 每次 Sonic 事件带 usage → 累加到 `interview.bidi_tokens_total`、`interview.bidi_cost_usd`。
- `interview.bidi_started_at` 于 SETUP→SPEAKING 首次跳转时置；`bidi_ended_at` 于终态跳转时置。

---

## 4. 状态机

### 4.1 服务端 Interview Session 状态

```
                  ┌──────────┐
   WS 连接 +      │          │
   "start" msg    │  SETUP   │  1) 加载 Interview + CompanyStyle + resume_context
   ───────────► │          │  2) QuestionService.generate_first() → Q1 文本
                  └────┬─────┘  3) 构造 BidiAgent system_prompt = company style + role + Q1
                       │        4) 启动 BidiAgent
                       ▼
                  ┌────────────┐   Sonic 输出音频帧 → 客户端 + buffer 到 q{idx}.pcm
                  │  SPEAKING  │◄──┐
                  │ (AI asks)  │   │ Sonic "outputTranscriptionCompleted":
                  └────┬───────┘   │   1) upload q{idx}.pcm → S3
                       │           │   2) update Question.question_audio_s3_key
                       ▼           │   3) 切 LISTENING
                  ┌────────────┐   │
                  │ LISTENING  │   │ 客户端 PCM → Sonic + buffer 到 a{idx}.pcm
                  │ (user ans) │   │ 静默 60s 超时计时器仅此状态有效（Tester #2）
                  └────┬───────┘   │
                       │ Sonic "inputTranscriptionCompleted" (end-of-turn)
                       ▼           │
                  ┌────────────┐   │
                  │ PERSISTING │   │ 1) upload a{idx}.pcm → S3
                  │            │   │ 2) persist Answer (transcript + duration + s3_key)
                  └────┬───────┘   │
                       │           │
              ┌────────┴───────┐   │
              │ N < target ?   │   │
              │ duration OK?   │   │ (BR-2 双限制)
              └─┬──────────┬───┘   │
                │ yes      │ no    │
                ▼          ▼       │
         ┌──────────┐  ┌────────┐  │
         │ NEXT_Q   │  │  END   │  │
         │ Qn+1 gen │  │        │  │
         └────┬─────┘  └────┬───┘  │
              │             │      │
              │ Claude OK   │      │
              └─────────────┼──────┘
                            ▼
                     ┌────────────┐
                     │ COMPLETED  │  interview.status="completed"
                     │            │  WS 发 "interview_complete" 后主动关闭 (1000)
                     └────────────┘

  NEXT_Q Claude 失败 3x（BR-3 降级）：
    → 跳至 END，interview.status="completed_degraded"
    → 若 N < target/2 改判 "abandoned"

  异常路径（任一状态触发）：
    - WS disconnect   → ABANDONED
    - Sonic setup/reconnect 3x failed → ABANDONED
    - duration 到且当前在 SPEAKING → 强制 END，当前 Question 无 Answer
```

### 4.2 状态枚举（Python）

```python
class SessionState(Enum):
    SETUP = "setup"
    SPEAKING = "speaking"       # AI 正在说话
    LISTENING = "listening"     # 用户正在回答
    PERSISTING = "persisting"   # 写 S3 + DB
    NEXT_Q = "next_q"           # Claude 生成下一题
    COMPLETED = "completed"
    ABANDONED = "abandoned"
```

---

## 5. WebSocket 协议

### 5.1 传输规范

- URL: `ws://<host>/ws/interview/{interview_id}`
- 消息帧：**全部 JSON**（包括音频 —— PCM16 bytes 用 base64 编码进 JSON）。
  > 决策说明：POC `agent.py` 已证明 Strands BidiAgent 的 `inputs`/`outputs` 都走 `receive_json`/`send_json`，bytes 在 `"data"` 字段内 base64；保持一致以复用 Strands 的 I/O 契约。binary WS frame 不用。
- 文本：UTF-8。
- 关闭码：1000 正常；4001 `interview_not_found`；4002 `already_connected`；4003 `setup_failed`。

### 5.2 Client → Server 消息

| type | payload | 时机 | 约束 |
|---|---|---|---|
| `start` | `{}` | WS 连接后首包 | 仅首次生效，重复发送被服务端**静默忽略**（Tester #4） |
| `bidi_audio_input` | `{data: base64_pcm16}` | 用户说话中 | 单帧解码后 PCM ≤ 32 KB（~1s 16kHz PCM16）；超限 → WS close 1009（Tester #5） |
| `end_of_interview` | `{}` | 用户主动结束（UI"提前结束"按钮） | — |

### 5.3 Server → Client 消息

| type | payload | 语义 |
|---|---|---|
| `session_ready` | `{question_count_target, duration_min}` | SETUP 完成，即将开播 |
| `question_start` | `{question_id, order, text}` | 本题开始（AI 开口前） |
| `bidi_audio_stream` | `{data: base64_pcm16}` | AI 语音帧 |
| `ai_speaking_end` | `{transcript}` | AI 该次发言结束 |
| `user_transcript_partial` | `{text}` | 用户 ASR 中间态（UI 实时显示） |
| `user_transcript_final` | `{text, question_id, duration_sec, timeout: bool}` | 本答结束；`timeout=true` 表示由静默超时触发，`text` 可能为空串（Arch #4） |
| `interview_complete` | `{status: "completed" \| "completed_degraded", question_count}` | 正常终止或降级终止（BR-3） |
| `error` | `{code, message, recoverable: bool}` | 异常（recoverable=false 客户端应关闭） |

### 5.4 协议不变式

- `session_ready` 之前客户端只能收到 `error`。
- 每个 `question_start` 之后、下一次 `question_start` 之前，恰好一次 `user_transcript_final`（`text` 可空，`timeout` 可 true）。
- `interview_complete` 之后服务端主动关闭 WS（1000）。
- `start` 消息收到一次后生效；后续 `start` 被服务端忽略，不回应也不关闭连接。

---

## 6. 数据流 & 组件交互

```
Browser (unit-4)                 WS Gateway (unit-2)                AWS
───────────────────              ───────────────────                ─────
POST /api/interviews ──────────► RecordService (unit-1) ─────────► SQLite
                                 { id, ws_url }
◄──── {id, ws_url} ─────────────

WS connect /ws/interview/{id} ─► InterviewEngineService
{"type":"start"}                  ├─► load Interview + CompanyStyle
                                  ├─► QuestionService.gen_q1() ──► Claude (Bedrock)
                                  ├─► persist Question(order=0)
                                  └─► spawn NovaSonicClient (BidiAgent)
                                            │
◄── session_ready ──────────────            │
◄── question_start(q0) ─────────            │
◄── bidi_audio_stream (frames) ─  ◄─ PCM ───┤ (BidiNovaSonicModel)
◄── ai_speaking_end ────────────            │
                                            │
PCM frames ──────────────────►  BidiSessionRecorder
                                  ├─► forward to BidiAgent
                                  └─► buffer to a{n}.pcm
◄── user_transcript_partial ────            │
                                            │
                                  end-of-turn detected
                                  ├─► s3_audio.upload(a{n}.pcm)
                                  ├─► persist Answer
◄── user_transcript_final ──────
                                  if N < target:
                                    QuestionService.gen_next() ──► Claude
                                    persist Question(order=n+1)
◄── question_start(q1) ─────────            │
                                  else:
                                    finalize_interview()
                                    update bidi_tokens_total / bidi_cost_usd
◄── interview_complete ─────────
WS closed (1000)
```

---

## 7. 关键模块接口（契约层，**非实现**）

### 7.1 InterviewEngineService

```python
class InterviewEngineService:
    async def run_session(
        self,
        websocket: WebSocket,
        interview_id: str,
    ) -> None:
        """
        完整状态机驱动：setup → speaking ↔ listening → completed/abandoned.
        正常返回表示 completed 或 abandoned；内部 catch 所有异常并更新 DB。
        """
```

### 7.2 QuestionService

```python
class QuestionService:
    async def generate_first(
        self, interview: Interview, company_style: CompanyStyle
    ) -> Question:
        """Q1：基于 role_title + company style + resume_context。"""

    async def generate_next(
        self, interview: Interview, company_style: CompanyStyle,
        history: list[tuple[Question, Answer]],
    ) -> Question:
        """Qn+1：带上 Q1..Qn + 答案 transcript，避免重复、递进深入。"""
```

### 7.3 NovaSonicClient（Strands 封装）

```python
class NovaSonicClient:
    def __init__(self, voice: str = "tiffany"): ...

    @asynccontextmanager
    async def session(self, system_prompt: str) -> AsyncIterator[BidiAgent]:
        """上下文管理：进入时启动 agent.run；退出时 agent.stop() 并捕获 usage 汇总。"""

    def last_usage(self) -> dict:
        """返回 {"input_tokens":..., "output_tokens":..., "cost_usd":...}，供成本计量。"""
```

### 7.4 BidiSessionRecorder

```python
class BidiSessionRecorder:
    def __init__(self, interview_id: str): ...
    def start_ai_turn(self, question_id: str, order: int) -> None: ...
    def append_ai_audio(self, pcm: bytes) -> None: ...
    def end_ai_turn(self) -> bytes:  # 返回完整 AI PCM，供 S3 上传
        ...
    def start_user_turn(self) -> None: ...
    def append_user_audio(self, pcm: bytes) -> None: ...
    def end_user_turn(self) -> tuple[bytes, float]:  # (pcm, duration_sec)
        ...
```

---

## 8. 错误处理矩阵

| 场景 | 处理 | 客户端提示 |
|---|---|---|
| `interview_id` 不存在 | SETUP 读 DB NULL → 100ms 重读一次（应对 SQLite WAL 的极短窗口，Tester #3）；仍无 → WS close 4001 | `interview_not_found` |
| 同一 interview 已有活跃 WS | WS close 4002 | `already_connected` |
| Sonic 建立失败（3x retry 失败） | WS close 4003 + interview.status=`abandoned` | `setup_failed`, recoverable=false |
| Sonic 中途断流 | 1x retry；仍失败 → 标 abandoned，保留已 persist 的 Q/A | `stream_lost`, recoverable=false |
| Claude Qn+1 失败（3x retry） | BR-3 降级：status=`completed_degraded`（或 `abandoned` 若 N < target/2） | 无单独提示；`interview_complete` 带 `status=completed_degraded` |
| S3 upload 失败（3x retry） | 对应 s3_key=NULL，transcript 保留；DB 其他字段正常 | 无；后续播放时前端降级（无音频 URL 时不显示播放器） |
| 客户端静默超时（LISTENING 状态 60s 无 PCM） | 服务端主动结束本题，进入 PERSISTING；`user_transcript_final` 带 `timeout=true, text=""` | `user_transcript_final{timeout:true}`（UI 可提示"未检测到语音，进入下一题"） |
| 单帧 PCM 超限（> 32 KB） | WS close 1009 | `frame_too_large` |
| WS 心跳丢失（30s 无任何帧，任一方向） | 标 abandoned | close 1011 |

**静默超时计时器规则**（Tester #2）：
- 仅在 `LISTENING` 状态下运行。
- 进入 `SPEAKING / PERSISTING / NEXT_Q` 时暂停并重置；回到 `LISTENING` 时重新计时。

---

## 9. 数据模型改动

**无新表**。复用 unit-1 的 `Interview / Question / Answer`。  
**仅使用**（非新增）的 Interview 字段：`bidi_tokens_total, bidi_cost_usd, bidi_started_at, bidi_ended_at, started_at, ended_at, status`。  
**新语义**：`status = "abandoned"` 可能由 unit-2 写入；`resume_context` 在面试结束时被 unit-2 清空（Req §5.1 隐私要求）。

---

## 10. 配置项（新增到 `config.py`）

| Key | Default | 用途 |
|---|---|---|
| `nova_sonic_model_id` | `amazon.nova-2-sonic-v1:0` | Sonic model |
| `nova_sonic_voice` | `tiffany` | Sonic voice |
| `bidi_user_silent_timeout_sec` | 60 | LISTENING 静默超时 |
| `bidi_ws_heartbeat_sec` | 30 | WS 心跳超时 |
| `bidi_max_frame_bytes` | 32768 | 单帧 PCM 上限（Tester #5） |
| `bidi_max_session_sec` | 0 (不限) | 硬截断单次 Sonic 会话时长，本地调试避免超支（Tester #6） |
| `public_ws_base_url` | "" (空则用 request.base_url) | 反向代理后的 WS 公开地址（Arch #5） |
| `question_default_target` | 8 | 默认题量（已有） |

---

## 11. Phase-2（unit-2 延伸，**不在本次交付**）

延后但已预留接口的能力：

1. **probe-on-weak**：`QuestionService.generate_next` 签名里已预留 `history`，Phase-2 加上 Claude 对最近一答评分 → 若 < threshold 则生成追问而非新主题。
2. **多 voice 切换**：配置已抽出。
3. **自定义 system_prompt 模板**：目前硬编码公司风格拼接；Phase-2 做模板化。

---

## 12. 测试策略

| 层级 | 关注点 | 策略 |
|---|---|---|
| 单元 | QuestionService / BidiSessionRecorder | Claude & Sonic 全 mock；状态机路径覆盖 |
| 契约 | WS 消息协议不变式（§5.4） | 用 pytest-asyncio + ASGI + `websockets` 客户端，脚本化驱动 |
| 集成（本地） | 真实 Nova Sonic + Claude | 单测脚本 `scripts/smoke_bidi.py`（不进 CI，避免钱） |
| e2e | 完整面试流程 | unit-4 frontend 上线后手测 |

---

## 13. 代码量预估

| 模块 | 预估行数 |
|---|---|
| `app/routers/bidi.py` (WS handler) | ~60 |
| `app/services/interview_engine_service.py`（状态机） | ~250 |
| `app/services/question_service.py` | ~100 |
| `app/services/bidi_session_recorder.py` | ~80 |
| `app/clients/nova_sonic.py` | ~80 |
| 测试 | ~300 |
| **合计** | **~870 行** |

---

## 14. 风险 & 缓解

| 风险 | 缓解 |
|---|---|
| Strands BidiAgent API 不稳（experimental 命名） | 版本锁 `strands-agents` 到 nova-sonic-poc 验证过的 version；单独 client 层隔离变动 |
| Sonic 事件名与 POC 推断不符 | 首日本地 probe.py 扩展：跑空对话，打印所有 event type，对齐 §5.3 |
| 长面试（45 min）内存泄漏 | 每题结束后 flush 音频 buffer；WS heartbeat 兜底 |
| 同一 interview 重复连接（**MVP 单实例假设**） | in-memory set `active_sessions` + 4002 close；**多实例部署需改用 DB lock 或 Redis，延后到运维阶段**（Arch #3） |
| 本地 smoke_bidi 频繁调真实 AWS 产生成本 | `bidi_max_session_sec` 硬截断；smoke 脚本跑前打印预估成本 + y/n 确认（Tester #6） |
| 反向代理后 `ws_url` host 错误 | `public_ws_base_url` 配置覆盖 request.base_url（Arch #5） |
