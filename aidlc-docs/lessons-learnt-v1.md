# Interviewer v1.0 — 复盘 Lessons Learnt

**日期**: 2026-05-02
**范围**: Sprint 1-8 (2026-04-25 ~ 2026-05-02, 8 天)
**交付**: 20 指标语音面试评估平台，128 自动化测试，生产部署

---

## 📊 项目数据

| 指标 | 数值 |
|---|---|
| 总开发时间 | ~8 天（含 POC 探索） |
| Sprint 数 | 8 |
| 自动化测试 | 128 pytest + 6 vitest = 134 |
| 代码行数 | ~5000 (backend) + ~1500 (frontend) + ~1000 (shared) |
| AWS 服务 | 6 (Nova Sonic, Claude, S3, Transcribe, Comprehend, Cognito) |
| 单面试成本 | ~$0.15 |
| 生产 bug 修复 | 8 次 |
| Team Review 轮次 | 12 次 (6 Requirements + 6 Code) |

---

## ✅ 做对了的事

### 1. Walking Skeleton 优先

**决策**: Sprint 1 就让语音流端到端跑通（浏览器 → WS → Nova Sonic → 回放），不做任何评估/持久化。

**效果**: 第一天就能"体验"产品，暴露了 Nova Sonic 的核心坑（hello.pcm bootstrap、turn_detection 必配）。如果先写评估逻辑再接语音流，这些坑会在第 3-4 天才发现，返工成本翻倍。

**Lesson**: **先让用户能"摸到"产品，再加功能。** Walking skeleton 不是偷懒，是风险管理。

### 2. 自动化测试从第一天开始

**决策**: 每个 Sprint 的 AC 都包含"测试全绿"。从 Sprint 1 的 6 个 test 到 v1.0 的 128 个。

**效果**: Sprint 6-8 大规模重构 voice_analyzer（从 dummy → 10 指标 → 14 指标 → 20 指标），每次改完跑 `pytest -q` 10 秒内确认没 regression。没有测试的话，每次改 rubric 公式都要手动验证 5 个 session × 5 个 answer = 25 个数据点。

**Lesson**: **测试不是"写完代码后补"的事，是"改代码时不崩"的保险。** 128 个测试 × 10 秒 = 每次改动 10 秒验证，比手动测 25 分钟快 150 倍。

### 3. AIDLC Team Review 真的能发现问题

**数据**: 12 次 team review，发现 **8 个 HIGH + 15 个 MED** issue。

**最有价值的 3 个发现**:
1. **architect Sprint 6**: "numpy 未安装" — 如果没核实就写代码，会在 EC2 部署时才发现缺依赖
2. **architect Sprint 7**: "leading pause 和 first_response_delay 重复计数" — 真实数据验证了 Q1 的 pause_count 从 8 降到 7，证明 review 发现的是真 bug
3. **senior-tester Sprint 6**: "`_compute_voice_features` 完全无单元测试" — 补了 4 个 async mock tests，后来 Sprint 8 改签名时这些测试立刻报错，避免了 silent regression

**Lesson**: **Review 不是形式主义。** 关键是 reviewer 有专业 checklist（skill Review Mode），不是泛泛地"看看有没有问题"。

### 4. 增量交付 + 真实数据验证

**模式**: 每个 Sprint 结束都用真实 141s session 回算验证。

**效果**: Sprint 6 发现 cps 4.95-7.14（用户语速偏快），Sprint 7 发现 Q1 首答延迟 15.36s（用户听题后长沉默），Sprint 8 发现 Q1 low_conf 18.5%（Transcribe 识别不出"呃/啊"）。每次都是**真实数据告诉我们阈值是否合理**，而不是拍脑袋。

**Lesson**: **不要在 staging 环境里调参数。** 用真实用户数据验证，1 个真实 session 比 100 个 synthetic test 有价值。

---

## ❌ 做错了的事 / 可以改进的

### 1. Epoxy 合规没提前了解

**事件**: Sprint 5 部署时给 EC2 开 :80 给 0.0.0.0/0，被 Amazon Epoxy 自动隔离（DyePack.EC2IPAuthentication）。Instance 被停机 + SG 换成完全无规则的 isolated SG。

**根因**: 不了解公司的安全合规自动化策略。以为"先部署再加 auth"是合理的 MVP 路径。

**应该做的**: 部署前先查 Epoxy/DyePack 规则，或者**一开始就用 CloudFront prefix list + Cognito**，不走"先暴露再收紧"的路径。

**Lesson**: **在公司环境里，"先 ship 再 secure" 不 work。** 合规自动化比你快。

### 2. Token 过期没在 Sprint 5 就处理

**事件**: Sprint 5 加了 Cognito auth，但没加 token refresh。用户 13 小时后访问 → 401。

**根因**: 只测了"登录 → 立刻用"的 happy path，没测"登录 → 隔天再用"。

**应该做的**: Sprint 5 的 AC 应该包含"token 过期后自动刷新"。Cognito access token 默认 1 小时，这是已知行为。

**Lesson**: **Auth 的 AC 必须包含 token lifecycle（获取 + 刷新 + 过期 + 登出）。** 只测"能登录"是不够的。

### 3. S3 CORS 没在 Sprint 4 就配

**事件**: Sprint 4 加了音频播放（presigned URL），但没配 S3 CORS。直到 Sprint 7 用户在 CloudFront 上点播放才发现跨域被拦。

**根因**: 本地开发时 S3 presigned URL 和前端同源（都是 localhost），不触发 CORS。部署到 CloudFront 后前端域名变了。

**应该做的**: 部署 checklist 应该包含"S3 CORS 配置"。

**Lesson**: **本地能跑 ≠ 生产能跑。** 部署 checklist 要覆盖：CORS、CSP、mixed content、cookie domain、WebSocket upgrade。

### 4. 评估 pipeline 耗时从 3 分钟涨到 4 分钟

**事件**: Sprint 8 加 Transcribe 后，evaluation 从 ~180s 涨到 ~220s（+40s）。5 个 Transcribe job 串行等待。

**根因**: `_compute_voice_features` 里 submit + wait 是串行的（每个 answer 等前一个完成才开始下一个）。

**应该做的**: 先并行 submit 5 个 job，再并行 wait。senior-dev review 提了但被推迟。

**Lesson**: **异步 job 的 submit 和 wait 应该分开。** 串行 submit 是 O(n×latency)，并行是 O(latency)。

---

## 🔑 技术 Lessons（可复用）

### Nova Sonic / Strands

1. **Sonic 永远不主动开口** — 必须注入 hello.pcm bootstrap。这不是 bug，是设计。
2. **175s 内部 timeout** — Strands 会自动 restart（BidiConnectionRestartEvent），你的代码不能在 restart 时 raise。
3. **ws.send_json 失败不能 raise** — 否则 TaskGroup 被 cancel，杀掉整个 session。swallow + log。
4. **turn_detection 必须显式配置** — V2 模型不会自动 VAD。

### SQLite + asyncio

5. **asyncio.create_task 的 GC 陷阱** — local 变量持有的 Task 会被 GC 回收 cancel。必须 module-level set 持有引用。
6. **StaticPool for in-memory test DB** — 否则每次 checkout 是独立 DB。
7. **DB lock 范围最小化** — S3 upload 不在 DB lock 内，否则 30s upload 阻塞所有 DB 写。

### AWS 服务集成

8. **Transcribe 不接受 raw PCM** — 必须加 44 字节 WAV header。文档没明确说，试了才知道。
9. **Transcribe job_name 幂等** — 用 `{interview_id}-{question_id}` 格式，重复提交不会 ConflictException。
10. **Comprehend DetectSentiment 有 5000 字节限制** — 长 transcript 要截断。
11. **S3 presigned URL 需要 CORS** — 浏览器直接 fetch S3 URL 时，S3 必须返回 `Access-Control-Allow-Origin`。
12. **EC2 暴露 HTTP 会被 Epoxy 隔离** — 必须 CloudFront prefix list + 应用层 auth。

### 前端

13. **AudioContext 必须在用户手势内创建** — 否则 auto-play policy 拦截。
14. **useSearchParams 需要 Suspense 包装** — Next.js 15 prerender 要求。
15. **Cognito token refresh 必须在 API 调用前** — 不能等 401 再 refresh（WS 连接没有 retry 机制）。

---

## 📈 AIDLC 方法论反思

### 有效的部分

- **Team Review 矩阵**（PM + architect 看需求，senior-dev + senior-tester 看代码）— 12 次 review 发现 8 HIGH，ROI 极高
- **主 session 加载 skill Review Mode** — 比 subagent dispatch 快 10 倍且更稳定
- **Requirements → Code → Test → Deploy → Verify 闭环** — 每个 Sprint 都有真实数据验证

### 可以简化的部分

- **Sprint 6-8 的 Requirements 文档**过于详细（138 行），对于"加 3 个指标"这种小 scope，50 行够了
- **Workflow Planning 阶段**对小 Sprint 价值不大（"跳过 stories/units/NFR" 本身就是 planning 的结论，但写出来花了 5 分钟）
- **audit.md 的时间线**太细（每个 AWS CLI 命令都记），对复盘有用但对日常开发是噪音

### 建议改进

1. **小 Sprint（< 2h）用 lightweight AIDLC**: Requirements 50 行 + 1 轮 review + 直接 code
2. **大 Sprint（> 4h）用 full AIDLC**: 完整 requirements + stories + design + 2 轮 review
3. **audit.md 分层**: 高层时间线（Sprint 级）+ 详细日志（只在 debug 时写）

---

## 🎯 v1.1 建议优先级（客户反馈后）

| 优先级 | 项目 | 预估 |
|---|---|---|
| P0 | 修 datetime.utcnow() deprecation (192 warnings) | 30min |
| P0 | 并行 Transcribe submit/wait (评估从 220s 降到 ~120s) | 1h |
| P1 | Playwright E2E 测试 (登录 → 面试 → 评估 → 历史) | 2h |
| P1 | PostgreSQL 迁移 (多用户并发) | 3h |
| P2 | WAF + rate limiting | 1h |
| P2 | Custom vocabulary (5G/RF/LNA 术语提高 Transcribe 准确率) | 1h |
| P3 | 多场景支持 (不只单一公司 RF) | 4h |
| P3 | 用户自助注册 (Cognito self-signup) | 1h |

---

*"Ship early, measure with real data, fix what matters."*
