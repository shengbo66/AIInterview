# Requirements — Mock Interview Platform (Interviewer)

**Document Version**: 1.1 (post-review revision)
**Date**: 2026-04-25
**Status**: Pending Approval

---

## 1. Intent Analysis

| Attribute | Value |
|---|---|
| **Request Type** | New Project (Greenfield) |
| **Scope Estimate** | System-wide (frontend + backend + AI services + storage) |
| **Complexity** | Complex |
| **Primary Target User** | 在校学生（校招准备） |
| **Current Phase** | MVP — 优先核心流程跑通，稳定后迭代到 Beta |

### 1.1 Product Vision

一个由 LLM 驱动的**模拟面试平台**，面向**在校学生校招准备**，提供**端到端语音模拟面试**体验，并通过 AI 给出**面试表现评估**和**逐题改进建议**，帮助用户提升真实面试表现。

### 1.2 Key Differentiators

1. **端到端语音交互**：使用 Amazon Nova Sonic 模型实现自然的双向语音对话
2. **可定制面试风格**：支持按公司（某公司、TCL、美的、字节、腾讯等）定制面试风格
3. **多维度评估**：内容、表达、语音维度三位一体
4. **时尚的 UI**：采用社区最新 UI 技术（Next.js 15 + shadcn/ui + Framer Motion），视觉对标 Linear / Vercel / Cal.com

---

## 2. Scope & Phases

### 2.1 MVP 阶段（本阶段目标）

**核心原则**：只做核心面试流程，跑通"端到端语音模拟面试 + AI 评估 + 记录回放"主链路。

**范围**：
- ✅ 核心面试流程（语音面试 + AI 评估 + 改进建议）
- ✅ 单用户面试记录列表 + 详情查看（无认证，默认单用户即自己）
- ✅ 先支持**行为面试 + 综合素质面试**（不含现场编程环境）
- ✅ 严格模式（一旦开始必须完成，不允许暂停）
- ✅ 整场面试一种语言（中文 or 英文）
- ✅ 内置 **2-3 家**常见公司面试风格 + 用户上传风格文档

**不在 MVP 范围**：
- ❌ 用户认证系统（Cognito）
- ❌ 管理后台
- ❌ 技术面试（需编程环境）
- ❌ 专业领域面试（产品/市场/财务等）
- ❌ 暂停/中断/宽松模式
- ❌ 面试中语言切换

### 2.2 Beta 阶段（后续迭代）

- 🔄 加入 Cognito 认证（用户注册/登录）
- 🔄 管理后台（查看所有用户面试记录、使用统计、题库管理）
- 🔄 存储从 SQLite 迁移到 PostgreSQL（Aurora Serverless v2）—— **见 Section 5.2 Migration Plan**
- 🔄 宽松模式（允许暂停）
- 🔄 技术面试（集成代码编辑器）
- 🔄 专业领域面试扩展
- 🔄 分享链接功能
- 🔄 管理员角色权限定义（**Open Questions 待定**）

---

## 3. Functional Requirements (MVP)

**优先级标注**：`[M]` Must / `[S]` Should / `[C]` Could

### FR-1: 面试前设置

**FR-1.1** `[M]` 用户进入图形化设置页面，配置本场面试参数：
- 面试公司（从内置列表选择 或 上传自定义公司风格文档）
- 目标岗位（文本输入）
- 面试时长 / 题目数量（默认：45-60 分钟，8-15 题；可自定义）
- 面试语言（中文 / 英文，整场统一）
- 可选：上传个人简历 / JD 作为 Claude 生成问题的 context

**Acceptance Criteria (FR-1.1)**:
- Given 用户打开设置页，When 选择公司 + 输入岗位 + 点击"开始面试"，Then 进入面试页面并触发 AI 打招呼
- Given 用户未选择公司或岗位为空，When 点击"开始面试"，Then 显示表单校验错误且不进入面试
- Given 用户上传简历 PDF，When 提交，Then 文件临时存储用于本次面试 Claude 调用，面试结束后从内存丢弃（MVP 不持久化简历）

**FR-1.2** `[S]` 系统内置 **2-3 家**常见公司面试风格数据（MVP：字节、Amazon、腾讯 三家起步），采用**结构化字段 + 补充说明文本**混合格式：
```
- 公司名
- 面试官风格标签（严谨 / 友好 / 压力型 / 技术深挖等）
- 偏好题型列表
- 常见题目示例（3-5 个）
- 补充说明文本（自由文本，供 Claude 作为 prompt context）
```

**FR-1.3** `[S]` 用户可上传自定义公司面试风格文档（Markdown 或纯文本，≤ 50KB）。

### FR-2: 面试进行中

**FR-2.1** `[M]` **端到端语音交互**：使用 Amazon Nova Sonic 实现双向语音流：
- AI 面试官用语音提问
- 用户用语音回答（麦克风录音）
- 实时流式交互（低延迟）

**Acceptance Criteria (FR-2.1)**:
- Given 用户已进入面试页，When AI 开始说话，Then 音频在 1.5 秒内从用户点击"开始"到听到 AI 首个音节
- Given 用户说完话 1 秒未再输入，When Nova Sonic 检测到语音结束，Then AI 在 1.5 秒内开始响应下一个问题或追问
- Given Nova Sonic 服务在面试中暂时不可用，When 语音流中断，Then 前端在 10 秒内展示"网络异常，面试终止"提示并将此次面试标记为 `abandoned`（保留已采集数据，见 FR-6.2）

**FR-2.2** `[M]` **严格模式**：面试一旦开始**不允许暂停或中断**。刷新页面或关闭标签页视为放弃。

**FR-2.3** `[M]` **动态问题生成**：由 Claude Sonnet 基于以下 context 动态生成问题：
- 所选公司面试风格
- 目标岗位
- 用户简历 / JD（如提供）
- 面试类型（行为 / 综合素质）
- 已回答的问题历史（实现追问 / 深挖能力）

**FR-2.4** `[M]` **UI 反馈**：面试进行中页面需展示：
- 当前题目编号 / 总题数
- 剩余时间（大致）
- AI 说话状态 / 用户说话状态的视觉指示
- 音波可视化（Framer Motion 动效）
- 当前题目的实时文字转录（subtle 显示，不抢视觉焦点）

### FR-3: 面试评估

**FR-3.1** `[M]` **评估维度**（三层递进）：
1. **内容维度**：回答准确性、完整性、STAR 结构、专业度
2. **表达维度**：逻辑清晰度、表达结构化、连贯性
3. **语音维度**：语速、停顿、流畅度、情感/自信度

**FR-3.2** `[M]` **评估生成**：面试结束后由 Claude Sonnet 生成：
- **整体评估报告**（总分 + 三维雷达图 + 总体评语 + 改进优先级）
- **每题详细分析**：原始问题、用户回答转录、三维评分、具体改进建议、理想范答

**Acceptance Criteria (FR-3.2)**:
- Given 用户完成面试，When 面试结束事件触发，Then 系统在 55 秒内生成完整评估报告
- Given 评估报告生成成功，When 用户查看报告，Then 每题都有：原始问题、用户回答转录、三维评分（0-100 数值 + 五星展示）、改进建议文本、理想范答文本
- Given Claude 调用失败，When 重试 2 次仍失败，Then 面试记录标记为 `evaluation_failed` 状态，用户可在记录详情页看到"报告生成失败，点击重试"按钮

**FR-3.3** `[M]` **评估延时**：评估异步生成。面试结束后用户看到"正在生成报告..."状态，报告生成完成后展示。

### FR-4: 面试记录

**FR-4.1** `[M]` **记录列表**：用户可查看所有历史面试记录，按时间倒序展示：
- 面试时间 / 公司 / 岗位 / 总分 / 状态

**FR-4.2** `[M]` **记录详情**：点击任一记录查看：
- 面试元数据 + 整体评估 + 每题详情（问题 + 转录 + 音频播放 + 评分 + 改进建议 + 理想范答）
- **音频回放体验**：文字转录按段落展示，**每段可点击播放**对应音频片段

**Acceptance Criteria (FR-4.2)**:
- Given 用户在记录列表点击某条记录，When 详情页加载完成，Then 首屏 2 秒内可见完整评估报告
- Given 详情页有一段用户回答转录，When 点击该段文字，Then 对应音频从该段开始播放
- Given 面试记录状态为 `abandoned`，When 查看详情，Then 显示"未完成"提示和已采集的部分数据，但无评估报告

**FR-4.3** `[S]` **导出**：
- 导出 PDF 报告（含题目、答案转录、评估、改进建议）
- 下载原始音频文件

**FR-4.4** `[S]` **删除**：用户可删除自己的面试记录（含 S3 音频文件）。

### FR-5: 数据持久化

**FR-5.1** `[M]` 面试记录（元数据、问答、评估）存储于 SQLite 数据库，**启用 WAL 模式**保证读写并发安全。
**FR-5.2** `[M]` 音频文件存储于 Amazon S3。
**FR-5.3** `[M]` 文字转录作为结构化数据存储（非仅音频）。

### FR-6: 错误处理（新增）

**FR-6.1** `[M]` **用户权限错误**：
- 麦克风权限被拒绝 → 首页提示"需要麦克风权限开始面试"+ 引导用户开启的说明
- 浏览器不支持 WebRTC/MediaRecorder → 引导用户使用 Chrome/Safari 最新版

**FR-6.2** `[M]` **面试中断数据保留策略**：
- 网络中断 / 浏览器崩溃 / 主动刷新 → 面试标记为 `abandoned`
- **已采集的音频片段和部分转录仍保留在 S3 和数据库**
- 记录列表中可见，标注"未完成"，不生成评估报告
- 用户可查看已采集的问答片段，也可删除此记录

**FR-6.3** `[M]` **外部服务不可用**：
- Bedrock Nova Sonic 不可用 → 面试开始前检测失败 → 提示"服务暂不可用，请稍后"
- 面试中 Nova Sonic 中断 → 10 秒超时后标记 `abandoned`
- Claude Sonnet 评估失败 → 自动重试 2 次 → 仍失败则标记 `evaluation_failed`，用户可手动触发重试
- S3 上传失败 → 本地临时缓存（浏览器 IndexedDB 或后端内存）+ 指数退避重试，最多 3 次；失败则面试标记为 `abandoned`

---

## 4. Non-Functional Requirements

### NFR-1: Performance

- **语音对话延迟**：用户说话结束到 AI 开始响应 ≤ 1.5 秒（**前提：后端与 Bedrock 同区域部署**）
- **页面首屏加载**：≤ 2 秒（国内 3G+ 网络）
- **评估报告生成**：≤ 55 秒完成整场面试的评估（基于中英双语 POC 实测：Transcribe + Claude 串行调用合理上限）

### NFR-2: Scalability（MVP 阶段宽松）

- MVP 并发用户：1-10 人
- Beta 阶段：支持 100 以内同时在线（此时必须完成 SQLite → PostgreSQL 迁移，见 Section 5.2）

### NFR-3: Security & Privacy

- HTTPS 全站加密
- SQLite 数据库文件系统层加密（EBS 加密卷）
- S3 bucket 加密（SSE-S3）+ 非公开访问（pre-signed URL 播放/下载）
- 用户可删除自己的记录（含 S3 音频）
- **MVP WebSocket 端点保护**（无认证阶段的基础防护）：
  - Referer / Origin 检查（限制从项目域名访问）
  - IP 级限流（单 IP 每小时最多 5 场面试）
  - 用户 Agent 检查（拒绝已知 bot）
  - 详细的费用监控 CloudWatch 告警（Bedrock 异常调用量报警）
- 不做 GDPR / 严格合规（MVP 简化）

### NFR-4: Reliability

- 面试过程中网络中断：FR-6.2 策略（标记 abandoned + 保留已采集数据）
- Bedrock Claude 调用失败重试：2 次指数退避
- S3 音频上传失败：本地缓存 + 3 次指数退避重试

### NFR-5: Usability

- **视觉风格**：时尚、现代、吸引学生用户；**对标 Linear / Vercel / Cal.com / Supabase 的设计语言**
- **关键动效**：音波可视化、评分动画、页面过渡采用 Framer Motion
- **响应式**：桌面 + 移动端适配（MVP 优先桌面）
- **无障碍**：遵循 WCAG 2.1 AA 基础要求（色彩对比度、键盘导航）
- **中英双语 UI**：可切换

### NFR-6: Cost Sensitivity

- 预算不敏感，追求最佳体验
- 使用 Nova Sonic + Claude Sonnet（不降级模型）
- S3 存储采用标准类，无自动过期

**NFR-6.1 单场面试成本预估**（以 45 分钟、8 题、中等详尽评估为基准）：

| 服务 | 成本 | 说明 |
|---|---|---|
| Nova Sonic | ~$1.50 | 双向语音约 90 分钟，按量计费估算 |
| Claude Sonnet | ~$0.80 | 评估约 20K input + 5K output tokens |
| S3 | ~$0.01 | 音频 ~50MB + PUT/GET |
| SQLite (EBS) | 忽略 | MVP 阶段包含在 ECS 容器成本 |
| **小计** | **~$2.30/场** | |

**NFR-6.2 预算预估**：
- MVP 阶段（10 用户，人均 5 场/月）：~$115/月 Bedrock + ECS/App Runner $30 + 其他 = **~$150/月**
- Beta 阶段（100 用户，人均 5 场/月）：~$1150/月 Bedrock + Aurora $40 + 其他 = **~$1200-1500/月**

（实际成本以 AWS Pricing Calculator 为准，建议部署前用 Cost Explorer 做一周的实际消耗观察并设置预算告警。）

---

## 5. Technical Stack (Confirmed)

| Layer | Technology | Notes |
|---|---|---|
| **Frontend** | Next.js 15 (App Router) + React 19 + TypeScript | 薄 BFF |
| **UI Components** | Tailwind CSS + shadcn/ui | 主组件库 |
| **Animations** | Framer Motion | 关键场景（音波、评分、过渡） |
| **AI SDK (Frontend)** | Vercel AI SDK | 流式响应 UI |
| **Backend** | Python 3.12 + FastAPI (async) | WebSocket + REST |
| **Backend Realtime** | FastAPI WebSocket | Nova Sonic 双向音频流 |
| **AI — Voice** | Amazon Bedrock Nova Sonic | 端到端语音 |
| **AI — Text** | Amazon Bedrock Claude Sonnet | 问题生成 + 评估 |
| **Database (MVP)** | SQLite (WAL mode) + SQLAlchemy 2.0 async + Alembic | 单文件数据库 |
| **Database (Beta)** | PostgreSQL (Aurora Serverless v2) | 迁移路径见 5.2 |
| **Audio Storage** | Amazon S3 | 原始音频文件 |
| **Deployment** | AWS (前端 Amplify；后端 ECS Fargate 或 App Runner) | 约束见 5.1 |
| **Auth (Beta)** | Amazon Cognito | MVP 不做 |

### 5.1 Deployment Constraints （新增）

**MVP 部署区域**：`us-east-1`（N. Virginia）

**理由**：
- Nova Sonic 当前主要可用于 us-east-1
- Claude Sonnet 稳定可用
- 如需其他区域，需在部署前验证 Bedrock 模型可用性或使用 cross-region inference（会增加延迟）

**后端部署约束**：
- 面试 WebSocket 端点 **必须部署在长连接友好环境**：**ECS Fargate** 或 **App Runner** 或 **EC2**
- **禁止使用 AWS Lambda 作为 WebSocket 端点**（Lambda 最长 15 分钟 + 冷启动不适合语音实时流）
- 无状态 REST API（用户设置、评估触发、记录查询）可以用 Lambda，但 MVP 为简化运维，**全部放在同一个 FastAPI 容器中**

**SQLite 并发约束**：
- 启用 WAL (Write-Ahead Logging) 模式：`PRAGMA journal_mode=WAL;`
- MVP 并发写入上限：约 5 个并发面试（实测值，超过会出现 `database is locked`）
- 超过此阈值必须迁移到 PostgreSQL

**音频格式链路**：

| 环节 | 格式 | 说明 |
|---|---|---|
| **浏览器采集** | `audio/webm;codecs=opus` | 通过 `MediaRecorder` API |
| **传输到后端** | WebM/Opus 二进制流 (via WebSocket) | 按 100-200ms 片段流式发送 |
| **后端转 Nova Sonic 输入** | LPCM 16-bit 16kHz mono | 使用 `ffmpeg-python` 或 `pydub` 转换 |
| **Nova Sonic 输出** | LPCM 16-bit 24kHz mono | Nova Sonic 返回格式 |
| **后端转前端播放** | WebM/Opus 或直接 PCM → Web Audio API 播放 | 延迟敏感，优先 PCM |
| **S3 存储** | WebM (用户) + WAV 或 MP3 (合成 AI 音频，可选) | WebM 体积小，回放兼容性好 |

### 5.2 Migration Plan: SQLite → PostgreSQL (Beta) （新增）

**触发条件**：以下任一条件满足即触发迁移：
- 并发用户超过 5 人
- 数据库文件超过 2GB
- 出现 `database is locked` 错误频繁

**迁移步骤**：
1. **准备**：在 Aurora Serverless v2 建库，结构由 Alembic migrations 自动创建（SQLAlchemy ORM 已确保 Postgres 兼容）
2. **数据导出**：使用 `pgloader` 工具或自写 Python 脚本导出 SQLite 数据
3. **类型转换**：
   - SQLite `TEXT` (JSON 字段) → PostgreSQL `JSONB`
   - SQLite `INTEGER PRIMARY KEY AUTOINCREMENT` → PostgreSQL `BIGSERIAL`
   - SQLite `DATETIME` → PostgreSQL `TIMESTAMPTZ`
4. **数据导入**：pgloader 或 COPY FROM
5. **校验**：对账记录数、关键字段值、外键完整性
6. **切换**：环境变量切换 DB connection string
7. **验证**：冒烟测试（创建面试、查询、评估）后上线
8. **回滚窗口**：保留 SQLite 文件 30 天

**停机窗口**：预计 30 分钟（小规模数据 < 1GB）

**S3 音频文件**：不受影响（路径不变）

---

## 6. Data Model (Initial, may evolve)

```
User (Beta only, MVP 单用户默认)
├── id, email, name, role (user/admin), created_at

Interview
├── id, user_id (nullable in MVP)
├── company_name, company_style_id (FK), role_title
├── language (zh/en), duration_min, question_count_target
├── mode (strict), status (in_progress / completed / abandoned / evaluation_failed)
├── started_at, ended_at, created_at

Question
├── id, interview_id (FK), order_index
├── question_text, question_audio_s3_key
├── generated_at

Answer
├── id, question_id (FK)
├── user_audio_s3_key, transcript_text
├── answered_at

Evaluation
├── id, interview_id (FK), question_id (nullable — overall if null)
├── content_score, expression_score, voice_score, overall_score
├── improvement_suggestion, ideal_answer (JSON — 灵活字段)
├── generated_at

CompanyStyle
├── id, name, interviewer_style_tags (JSON)
├── preferred_question_types (JSON), sample_questions (JSON)
├── prompt_context_text, is_builtin, created_by (nullable)
```

---

## 7. User Flows (High Level)

### Flow 1: 完成一场面试

```
1. 用户进入首页 → 点击"开始模拟面试"
2. 设置页面：选公司 + 输岗位 + (可选上传简历) + 选语言 → 确认
3. 面试页面：
   - AI 语音打招呼 + 介绍规则
   - Q&A 循环（AI 提问 → 用户语音回答 → AI 追问/下一题）
   - UI 显示：题号进度、音波动画、实时转录
4. 面试结束：显示"正在生成评估报告..." → 报告生成后跳转详情页
5. 详情页：整体评估 + 每题分析 + 音频回放
```

### Flow 2: 查看历史记录

```
1. 首页 → 点击"我的面试记录"
2. 列表页：卡片式展示所有历史面试
3. 点击某条记录 → 详情页（同 Flow 1 step 5）
4. 可操作：导出 PDF、下载音频、删除记录
```

### Flow 3: 异常中断

```
1. 用户面试进行中 → 网络断开 / 刷新页面 / 关闭标签
2. 后端 WebSocket 断开 10 秒无重连 → 标记 interview.status = abandoned
3. 已采集音频和转录保留在 S3 和 DB
4. 用户下次打开 → 记录列表显示该条为"未完成"
5. 用户可查看已采集片段或删除
```

---

## 8. Open Questions / Future Considerations

| Topic | Current Decision | Future Action |
|---|---|---|
| 技术面试（编程） | MVP 不做 | Beta 集成代码编辑器（Monaco / CodeMirror） |
| 管理后台 | MVP 不做 | Beta 加入，含使用统计、题库管理、跨用户查询 |
| 认证系统 | MVP 不做 | Beta 集成 Cognito |
| 存储演进 | MVP SQLite (WAL) | Beta 按 5.2 Migration Plan 迁移到 PostgreSQL |
| 宽松模式（暂停） | MVP 不做 | Beta 加入 |
| 面试语言切换 | MVP 整场一种 | Beta 可考虑题级切换 |
| 分享功能 | 不做 | Beta 可评估 |
| 实时提示 | 不做 | 未来可评估 |
| 视频维度 | 不做 | 未来可评估 |
| 管理员权限边界 | MVP 无，Beta 待定 | Beta 阶段定义：只读 vs 可删除 vs 可编辑用户数据 |
| 简历持久化 | MVP 不持久化 | Beta 可选：用户可保存常用简历模板 |

---

## 9. Success Criteria (MVP)

MVP 被认为成功的标准：

1. ✅ 用户可完成一场 45 分钟的端到端语音模拟面试，全程无 crash
2. ✅ 面试结束后 55 秒内生成评估报告，含三维评分和每题改进建议
3. ✅ 用户可查看任一历史面试详情，包括音频回放（按段落点击播放）
4. ✅ 经过 **5 人以上学生 beta 测试反馈**，UI/体验平均评分 ≥ 4/5（视觉对标 Linear / Vercel / Cal.com）
5. ✅ 语音交互延迟 ≤ 1.5 秒（同区域部署前提下）
6. ✅ 至少内置 **2-3 家**公司面试风格，且用户可上传自定义风格
7. ✅ 错误场景（麦克风拒绝、网络中断、Bedrock 异常）有清晰用户反馈

---

## 10. Summary

**产品一句话**：一个用 Nova Sonic 语音 + Claude Sonnet 评估、采用社区最新 UI 技术（Next.js 15 + shadcn/ui + Framer Motion）打造的**学生校招模拟面试平台**，MVP 聚焦行为/综合素质面试，严格模式单次通关，完整记录可回放并提供 AI 改进建议。

**技术栈一句话**：Next.js 15 前端 + Python FastAPI 后端（ECS Fargate，us-east-1）+ SQLite (WAL)/S3 存储 + AWS Bedrock（Nova Sonic + Claude Sonnet）。

**MVP 边界一句话**：不做认证、不做管理后台、不做技术面试、不做宽松模式——把核心语音面试+评估+记录回放做到最好，其他留给 Beta。

**Revision 1.1 新增**：每个 FR 加了 Must/Should/Could 优先级 + 核心 FR 加 Given/When/Then 验收标准 + Section 5.1 部署约束 + Section 5.2 迁移计划 + FR-6 错误处理 + NFR-6.1 成本预估 + NFR-3 WebSocket 基础防护。

---

## 11. Phase 0: 评估算法 POC Gate（v1.2 新增）

**背景**：面试评估是本产品的核心价值。在进入 MVP 开发前，必须先验证评估算法的可行性，避免 MVP 实现后发现核心算法不可用。

### 11.1 架构选型（确认）

**语音维度评估方案**：
- **对话**：Amazon Bedrock Nova Sonic（端到端语音对话）
- **语音分析**：Amazon Transcribe Call Analytics（sentiment、talk speed、silence、interruption 等指标）
- **文本评估**：Amazon Bedrock Claude Sonnet（综合 transcript + 语音指标 + rubric 输出评分）
- **原则**：全部使用 AWS 托管服务，不自建模型

### 11.2 Phase 0 范围

Phase 0 **只验证评估算法**，不做 UI / 数据库 / 完整流程：

**Phase 0.1 — 合成样本验证**（优先）：
- Claude 生成"好/中/差"三组面试对话脚本
- Amazon Polly 合成音频（问题 + 答案）
- Transcribe Call Analytics + Claude Sonnet 评估
- **Gate 1**: 算法能区分好/中/差 → 继续；否则算法 revise

**Phase 0.2 — 真实样本验证**：
- 录制 2-3 段真实面试回答音频
- 跑同一套评估流程
- **Gate 2**: 真实录音评估结果合理（评语引用客观指标、改进建议可操作）→ Phase 0 PASS

### 11.3 Phase 0 验收标准

| # | 标准 |
|---|---|
| 1 | 合成样本（好/中/差）三维评分有显著差异（任意两级总分差 ≥ 15 分） |
| 2 | 同一段录音运行 3 次，**overall_result 分类标签一致**（Pass/Borderline/No-Pass）— 分类级别一致性，贴近用户实际体验（用户看 label 不看精确分数） |
| 3 | 评语引用至少 1 个客观指标数值 |
| 4 | 单场评估（Transcribe + Claude）耗时 ≤ 55 秒（原 30s/45s 迭代调整：中文 Transcribe 较慢 + Claude 生成长输出 ~20s + S3/启动 overhead，合理上限） |
| 5 | 单场评估成本 ≤ $4 |
| 6 | 改进建议人工审核：10 份样本中 ≥ 8 份"具体可操作"（非"继续努力"等空话）|

### 11.4 Phase 0 产出物

```
aidlc-docs/construction/phase0-poc/
├── poc-plan.md
├── rubric.md
├── prompts/evaluation-prompt-v1.md
├── samples/ (合成 + 真实)
├── results/ (JSON + 可区分度分析)
└── poc-verdict.md
```

代码：`poc/` 下单文件 Python 脚本（~300 行，命令行工具，无前端）。

### 11.5 Phase 0 → MVP 门槛

**必须**：Phase 0 所有 6 条验收标准通过后才进入 MVP 实现。未通过则 revise prompt/rubric 或调整架构。

### 11.6 Phase 0 成本预估

| 项 | 成本 |
|---|---|
| Phase 0.1 合成样本（Claude 脚本 + Polly + Transcribe + Claude 评估 ×3） | ~$3.40 |
| Phase 0.2 真实样本（Transcribe + Claude 评估 ×3） | ~$2.80 |
| **Phase 0 总计** | **< $10** |

### 11.7 评估算法设计（待 Phase 0 最终定稿）

**评分粒度**：Rubric-based（5 级评分，不拆子维度）
**评估单元**：双阶段（每题独立评估 + 全局复审）
**语音维度**：客观指标（Transcribe Call Analytics 输出） + Claude 解读
**公司风格**：作为 Claude prompt 的偏好输入，分数刻度统一
**理想范答**：面试结束时每题生成一份参考答案（MVP 阶段）
**可审计性**：记录每次评估的 prompt + response（JSON 字段 `Evaluation.raw_prompt` + `raw_response`）

### 11.8 对数据模型的影响

```
Evaluation 增加字段:
├── voice_features (JSON) — Transcribe Call Analytics 原始输出 + 轻补充
├── rubric_version (TEXT) — 评分 rubric 版本号
├── raw_prompt (TEXT) — 评估 prompt（可审计）
├── raw_response (JSON) — Claude 原始返回
└── evaluation_cost (REAL) — 本次评估花费（美元，便于成本跟踪）
```

### 11.9 对 NFR 的影响

- **NFR-1 Performance**：评估 ≤ 45 秒（由两次串行 API 调用组成：Transcribe ~15-20s + Claude ~20s）
- **NFR-6 Cost**：单场成本 $2.30 → **$3.40**，MVP 月预算 $150 → **$170**

