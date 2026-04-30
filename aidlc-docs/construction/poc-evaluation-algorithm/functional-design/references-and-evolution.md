# References & Evolution Directions

**Purpose**: 追踪社区参考方案，记录可借鉴点与演进方向。当 POC 或 MVP 遇到问题时，这里有明确的迭代方向，避免从零思考。

**Last Updated**: 2026-04-25

---

## 1. 参考项目清单

### 1.1 Tameyer41/liftoff ⭐1.5k [TypeScript, Next.js]

**GitHub**: https://github.com/Tameyer41/liftoff
**Demo**: https://demo.useliftoff.com

**核心架构**:
- 前端：Next.js + Tailwind + Framer Motion + HeadlessUI
- 音频：浏览器录制（React Webcam）+ **FFmpeg.wasm 在浏览器端转码**
- 评估：OpenAI Whisper（转录）+ GPT（评估）
- 部署：Vercel（serverless）

**对我们的借鉴价值**: ⭐⭐⭐⭐
**可借鉴点**:
- [ ] **FFmpeg.wasm 浏览器端音频转码** — 未来可考虑切换到浏览器转码（降低后端 ECS 成本 + 减少网络传输）
- [ ] **Stripe Gradient Animation 视觉效果**（Mesh Gradient，用 WebGL）— 前端"时尚感"参考
- [ ] **Upstash Redis 做限流** — 如果 MVP 阶段 WebSocket 裸露公网需要限流，Upstash 是 serverless 友好方案

**我们不同**: 使用 Bedrock（不是 OpenAI）+ FastAPI 后端（不是 Next.js serverless）+ 视频不是核心（我们只做音频）

---

### 1.2 adrianhajdin/ai_mock_interviews (Prepwise) ⭐518 [TypeScript]

**GitHub**: https://github.com/adrianhajdin/ai_mock_interviews
**教程**: JavaScript Mastery YouTube

**核心架构**:
- 前端：Next.js + Tailwind + shadcn/ui
- 语音：**Vapi AI**（第三方语音 agent 托管平台）
- AI：Google Gemini（问题生成 + 评估）
- 后端：Firebase（Auth + Firestore）

**对我们的借鉴价值**: ⭐⭐⭐
**可借鉴点**:
- [ ] **Vapi AI 的语音 agent 编排经验** — 如果 Nova Sonic 遇到严重问题，Vapi 是可行备选（但不是 AWS 原生，违反"托管服务"原则）
- [ ] **UI 组件选型**（shadcn/ui + Tailwind）— 我们已采用
- [ ] **Dashboard 设计参考** — 面试记录列表的卡片布局

**我们不同**: 不用 Vapi，直接用 Bedrock Nova Sonic；不用 Firebase，用 SQLite + 自建 FastAPI

---

### 1.3 zixi-liu/interview-ai-prototype ⭐115 [Python] 🌟最相关

**GitHub**: https://github.com/zixi-liu/interview-ai-prototype

**核心价值**: **与我们评估算法最接近的参考**

**评估结构（已采纳）**:
- FAANG 6 competencies: Ownership / Problem Solving / Execution / Collaboration / Communication / Leadership-Influence / Culture Fit
- STAR Method 4 要素
- **Pass/No-Pass checkpoint** 而不是纯数字（我们 v1.1 已采纳）
- Overall Result: Pass / No-Pass / Borderline（我们 v1.1 已采纳）

**Prompt 设计（已参考）**:
- Temperature 0.3
- 结构化 checkpoints 输出
- Prioritized feedback list

**模型选型**:
- 默认 gpt-4o-mini（成本敏感版）+ gpt-4o-audio-preview（支持音频直接输入）

**对我们的借鉴价值**: ⭐⭐⭐⭐⭐
**可借鉴点 / 演进方向**:
- [x] **FAANG checkpoints 结构**（已融入 v1.1 rubric）
- [x] **Pass/No-Pass + 数字双层输出**（已融入 v1.1）
- [ ] **HybridStopPolicy**（policy/stop_policy.py） — 这是他们判断"是否追问"的策略，我们 MVP 的问题生成可借鉴
- [ ] **LiteLLM 而不是直接 SDK** — 如果需要快速切换模型（Claude / GPT / Gemini 对比），LiteLLM 是统一接口
- [ ] **gpt-4o-audio-preview 直接处理音频** — 如果 Transcribe Call Analytics 中文效果差，OpenAI 的 audio preview 是备选

**预先分析**（深挖其 `prompts.py`）:
- 对"自我介绍"和"行为题"有**不同的 prompt 模板** — 我们可以在 MVP v1.1 针对不同题型定制
- 行为题的 checkpoint 包括 STAR / Specificity / Impact / Leadership / Problem-Solving / Communication — 比通用评分更针对

---

### 1.4 pigna90/ai-mock-interviewer ⭐16 [Python, CrewAI]

**GitHub**: https://github.com/pigna90/ai-mock-interviewer

**核心价值**: **多 agent 架构参考**

**架构**:
- CrewAI 框架下两个 agent：Interviewer + Evaluator
- 两者协作：Interviewer 问 → Evaluator 看 → Interviewer 决定追问

**对我们的借鉴价值**: ⭐⭐⭐
**演进方向**:
- [ ] **Interviewer + Evaluator 角色分离** — 当前我们是 Nova Sonic 既对话又出转录，Claude 单独评估。未来可以考虑：**Claude 在面试进行中作为 silent evaluator**，实时判断是否需要追问（当前 US-008 动态问题生成的升级方向）
- [ ] **CrewAI / LangGraph 多 agent 编排框架** — 当业务复杂度提升（如加入"技术面试 agent"、"行为面试 agent"）时的架构参考

**我们不同**: MVP 用单一 Claude 调用，不引入多 agent 框架（避免 MVP 过度复杂）

---

### 1.5 Azzedde/aiva_mock_interviews ⭐72 [Python]

**GitHub**: https://github.com/Azzedde/aiva_mock_interviews

**核心价值**: Docker 化部署参考 + interview_questions.json 题库结构

**对我们的借鉴价值**: ⭐⭐
**可借鉴点**:
- [ ] **interview_questions.json 题库 schema** — 如果 MVP 需要预置部分问题（保持 fallback），可以参考其 JSON 结构

---

## 2. 演进方向 (Evolution Roadmap)

**触发条件 → 借鉴方案** 映射表。POC 或 MVP 实施时遇到问题，直接查这张表：

| 场景 / 问题 | 借鉴项目 | 演进方案 |
|---|---|---|
| Nova Sonic 在 us-east-1 之外区域不可用 | liftoff | 备选：OpenAI Whisper + GPT-4o（非 AWS）|
| Transcribe Call Analytics 中文支持差 | zixi-liu | 备选：gpt-4o-audio-preview（直接处理音频，跳过 Transcribe）|
| MVP 后端 ECS 音频转码成本高 | liftoff | 切换到 **FFmpeg.wasm 浏览器端转码** |
| 需要实时追问逻辑更智能 | zixi-liu (HybridStopPolicy), pigna90 | 引入 silent evaluator agent / 多 agent 编排 |
| 需要支持多题型差异化 prompt | zixi-liu | 按题型独立 prompt 模板（行为 / 技术 / 综合）|
| MVP v2 要支持模型切换对比 | zixi-liu (LiteLLM) | 引入 LiteLLM 统一接口 |
| WebSocket 裸露防 Bedrock 刷费 | liftoff (Upstash) | Redis rate limiting |
| 评估结果不稳定，方差大 | zixi-liu | 降低 temperature 到 0.1 + structured output + JSON schema validation |
| 用户觉得数字分数不直观 | zixi-liu (已采纳) | Pass/No-Pass + Reason 为主展示 |
| 需要情感/语气的深度分析 | ~~社区普遍不做~~ | **没有明确参考**，保持现有 Transcribe Call Analytics + 客观指标方案 |

---

## 3. 调研过程记录

**调研时间**: 2026-04-25 23:25
**调研方式**: GitHub Search API
**关键词**: `mock-interview in:name`, `ai-interviewer in:name`, `interview+coach+ai`, `interview+simulator+ai`

**关键发现（总结）**:
1. 社区主流是"**语音转录 + 文本 LLM 评估**"（Whisper/Vapi + GPT），没人真的在做音频信号情感分析
2. 评估结构倾向 **Pass/No-Pass + checkpoint reasoning**，而不是纯数字打分
3. FAANG 行为面试已有公认 rubric，无需自己设计
4. 我们的 Bedrock 选型在社区少见（大多用 OpenAI），但符合用户"托管服务"约束

**未找到的**:
- ❌ 专门用 AWS Bedrock + Nova Sonic 做面试评估的开源项目
- ❌ 专门针对"中国学生 / 中文面试"的方案
- ❌ 用 Transcribe Call Analytics 做语音质量评估的开源实现

**结论**: 我们的方案在 AWS 生态内是**相对领先**的实现，需要自己蹚一些路；但评估算法本身（FAANG rubric + Pass/No-Pass）有成熟参考，降低了创新风险。

---

## 4. 如何使用本文档

1. **POC 失败或效果不理想时** → 查 "演进方向映射表"，找到对应备选方案
2. **MVP 迭代规划时** → 看 "可借鉴点未勾选项"，评估是否纳入
3. **新需求出现时** → 回来检查是否有新的社区方案（定期更新）
4. **遇到"这个设计是怎么来的"问题时** → 回溯到具体参考项目

**下次更新时机**:
- POC Gate 不通过时
- MVP 开发遇到架构瓶颈时
- Beta 阶段规划时
- 每 6 个月主动 review（社区演进快）


---

## Evolution Log — 2026-04-26 PoC 实跑发现

### 新增演进方向

| 场景 / 问题 | 触发条件 | 演进方案 |
|---|---|---|
| Transcribe Batch Job 队列延迟不可预测（实测 50s-293s 抖动） | MVP 异步 UX 不够，或有评估延迟 SLA 需求 | **Transcribe Streaming API**（WebSocket 实时转录） |
| AC2 纯数值方差对边界 case 不稳定 | 需精确评分时 | 降 temperature 到 0.1 + structured output；或改用 JSON schema constrained decoding |
| 中文长文本 Claude 生成略慢 | 需控制 P99 延迟 | 减 `max_tokens` + 精简 prompt；或 streaming response（前端增量渲染） |

### 验证的决策

- **FAANG 6-checkpoint rubric** 在中英文都稳定（分类级别 100% 一致）
- **双层输出**（Pass/No-Pass 标签 + 数字分数）设计对了——用户认标签，数字做图表
- **托管服务组合**（Polly + Transcribe + Bedrock Claude）端到端可行，成本 $0.05/场远低预算

### 失败的假设

- ❌ "评估 ≤ 30s" — AWS Batch Job 不现实
- ❌ "Call Analytics 适合 monologue 面试" — 需要 ≥2 channel，不适用
- ❌ "Claude Sonnet 4" — 已 Legacy，应用 Sonnet 4.5（inference profile）
