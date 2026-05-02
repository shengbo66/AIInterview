# Sprint 3 Delta Requirements

> Scope: 把 Sprint 2 已经持久化的面试数据**第一次暴露给用户**，并添加 AI 评估。
> Basis: `requirements.md` v1.2 FR-3 (评估) 和 FR-4 (记录列表/详情)。本文是 Sprint 3 的增量细化。
> Depth: minimal — 简单 feature、现有 schema/API 已覆盖大部分后端、风险低。

---

## 1. User Value

**当前痛点**（Sprint 2 结束状态）：
- 用户完成面试后，数据都落库了，但**看不到**——只能看 transcript 在 UI 上闪过，一刷新就消失
- 没有任何"我表现如何"的反馈，体验就是"说了一通话，然后呢？"

**Sprint 3 交付后**：
- 用户可以**浏览历史面试列表**，看到日期、时长、题目数等基础元数据
- 用户可以**点进某一场**，看每一轮问答的文本 + 基本指标
- 面试结束后 AI 给出**整体评估 + 逐题改进建议**，用户能知道"哪些答得好 / 哪些该改进"

---

## 2. In Scope (Sprint 3)

### S2-3: 历史列表 + 详情页（纯前端 + 使用现有 REST API）

**S2-3.1 历史列表页 `/history`**
- 列出所有 interview，按 `started_at` desc
- 每条显示：时间（YYYY-MM-DD HH:mm）、状态（进行中 / 已完成 / 评估中 / 已评估）、题数、总时长、公司/岗位（某公司 · RF Intern）
- 空状态：提示"还没有面试记录，点击开始面试"
- 点击一条 → 跳转到详情页 `/history/:id`

**S2-3.2 详情页 `/history/:id`**
- Header 区：元数据（时间、状态、公司/岗位、总时长、tokens/cost）
- Timeline：按 order_index 展示每一轮 `Question → Answer` 对
  - 每轮显示：问题文本、回答转录文本、回答时长
  - 音频播放按钮（有 `s3_key` 时可播放；Sprint 3 不要求流畅度，能播即可）
- 评估区：整体评分、三维分数、改进建议列表（Sprint 3 依赖 S2-4 完成）

**S2-3.3 首页入口**
- 当前单页 UI 加一个"查看历史"按钮，跳 `/history`

---

### S2-4: 评估报告 pipeline（后端 + Claude）

**S2-4.1 评估触发**
- interview.status 从 `in_progress` → `completed` 时（`bidi_ended_at` 被写入），**自动**触发评估
- 触发方式：`BidiInterviewSession.finalize()` 完成后 spawn background task `evaluate_interview(interview_id)`

**S2-4.2 评估逻辑**
- 复用 `shared/eval_core/` 的 rubric + prompt_template（POC 已 PASS 验证）
- 输入：interview 的所有 `(question.text, answer.transcript_text, answer.duration_sec)` 对
- 调用 Claude Sonnet 4.5（通过 `app/clients/bedrock_claude.py`）
- 输出 JSON: `{overall_score, content_score, expression_score, voice_score, overall_comment, per_question: [{score, feedback, ideal_answer}, ...]}`
- 持久化到 `Evaluation` 表（schema 已有，field 见 `models.py`）

**S2-4.3 评估状态机**
- `evaluation_status` 字段：`pending`（默认）| `generating` | `completed` | `failed`
- failed 重试 ≤ 2 次（FR-3 规定）

**S2-4.4 评估 REST API**
- `GET /api/interviews/{id}/evaluation` → 返回 Evaluation 或 404
- `POST /api/interviews/{id}/evaluation/retry` → 手动重试（failed 状态可用）

---

## 3. Out of Scope (Sprint 3)

- ❌ 音频流式回放（需要 S3 presigned URL + HTML5 audio，留 Sprint 4）
- ❌ 语音维度评估（voice_features 计算依赖音频文件解析，留 Sprint 4）—— S2-4 先只做 content + expression 两维，voice 置 null
- ❌ 多用户 / 认证（M0 明确单用户）
- ❌ PDF 导出
- ❌ 评估结果修改 / 反馈机制
- ❌ 删除 / 归档面试记录（前端暂不暴露）

---

## 4. Acceptance Criteria

### S2-3 验收
- **AC-3.1** Given 用户访问 `/history`，When 数据库有 ≥1 场面试，Then 列表正确展示且按时间倒序
- **AC-3.2** Given 用户访问 `/history`，When 数据库为空，Then 显示"还没有面试记录"空状态
- **AC-3.3** Given 用户点击某条记录，When 详情页加载，Then 显示该面试的所有 Q/A 对、元数据、评估（或"评估生成中"状态）
- **AC-3.4** Given 一场面试 status=`abandoned`（客户端中途断开），When 查看详情，Then 不触发评估，显示"未完成"提示

### S2-4 验收
- **AC-4.1** Given 一场面试正常结束（finalize 成功），When 1 分钟内查询 evaluation，Then 状态由 `pending` 经 `generating` 变为 `completed`，有完整 JSON
- **AC-4.2** Given Claude 调用失败（网络 / rate limit），When 系统捕获异常，Then 重试最多 2 次，2 次后标记 `failed` 并保存错误信息
- **AC-4.3** Given 面试 Q/A 数据为空（0 题或全部 answer 为空），When 触发评估，Then 跳过 Claude 调用，evaluation_status = `skipped`，不算 failed
- **AC-4.4** 自动化测试覆盖：evaluation 成功 / Claude 失败重试 / 空面试跳过 / status 状态机推进

---

## 5. NFRs

- **Evaluation 延时**：FR-3 规定 ≤ 55s，POC 实测 ~10-15s，不挑战
- **成本**：每次 Claude 评估 ~$0.02-0.05（POC 实测），Sprint 3 实验期不封顶
- **历史列表性能**：<100 条记录时，初始加载 ≤ 500ms。大量记录不做分页（留 Sprint 4）
- **详情页首屏**：2 秒内（FR-4.3 规定）
- **评估并发**：单用户 M0 场景无并发压力，background task 串行即可

---

## 6. Dependencies

- ✅ `shared/eval_core/` rubric/prompt_template（POC PASS）
- ✅ `app/clients/bedrock_claude.py`（unit-1 已实现）
- ✅ `Evaluation` 表 schema（unit-1 已建）
- ✅ REST endpoints `GET /api/interviews` + `GET /api/interviews/{id}`（unit-1 已有）
- 🆕 需新增：`GET /api/interviews/{id}/evaluation`、retry endpoint
- 🆕 需新增：`app/services/evaluation_service.py` 或 `record_service.py` 扩展
- 🆕 需新增：前端 `/history` + `/history/[id]` 页面

---

## 7. Risks

| 风险 | 影响 | 缓解 |
|---|---|---|
| Claude 返回 JSON 格式不稳定 | 评估入库失败 | prompt 强制 JSON schema，解析失败重试 1 次后 fallback 到文本 |
| Evaluation 生成期间用户开新面试 | 后台 task 冲突？| 每个 interview 独立 task，无共享状态，OK |
| 前端音频播放依赖 presigned URL | Sprint 4 再做 | Sprint 3 不做音频播放 |
| 详情页数据量大（45 轮 × 1KB transcript）| UI 卡顿 | 测试时验证 50 条渲染 ≤ 100ms，必要时虚拟列表（留 Sprint 4） |

---

## 8. Success Metrics

- Sprint 3 结束后，用户可以完整体验：**开始面试 → 面试结束 → 进历史列表 → 点进详情 → 看到评估报告**
- 自动化测试 58+ → 70+（S2-3 纯前端组件测试 + S2-4 后端评估 pipeline 测试）
- 无 production-style 手工 bug（靠 ws_smoke + Vitest + pytest 自动抓）
