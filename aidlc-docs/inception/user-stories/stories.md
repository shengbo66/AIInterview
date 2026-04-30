# User Stories — Mock Interview Platform (MVP)

**Document Version**: 1.1 (v1.1 新增 Phase 0 POC story)
**Date**: 2026-04-25
**Scope**: Phase 0 (POC) + MVP (Beta stories deferred)
**Primary Persona**: 林可（在校学生求职者）

**Priority Legend**: `[M]` Must / `[S]` Should / `[C]` Could
**INVEST Compliance**: 每个 story Independent / Negotiable / Valuable / Estimable / Small / Testable

---

# Phase 0: 评估算法 POC

## US-000 [M] 验证评估算法可行性（Phase 0 Gate）

**As a** 产品负责人（你）
**I want** 在进入 MVP 开发前用合成样本 + 真实样本验证评估算法（Transcribe Call Analytics + Claude Sonnet）
**So that** 避免在 MVP 实现后才发现核心算法不可用

**Acceptance Criteria**

- Given Phase 0.1 合成样本（Claude 生成的"好/中/差"面试对话 + Polly 合成音频）
- When 跑评估流程（Transcribe Call Analytics + Claude Sonnet）
- Then 三级样本的三维评分两两之间总分差 ≥ 15 分

- Given 同一段录音
- When 运行评估 3 次
- Then **overall_result 分类标签一致**（Pass/Borderline/No-Pass）—— 分类级别一致性

- Given 评估完成
- When 查看 Claude 输出评语
- Then 评语中至少引用 1 个客观指标数值（语速/停顿/填充词）

- Given 单次评估开始
- When 等待完成
- Then 耗时 ≤ 55 秒

- Given 10 份样本评估完成
- When 人工审核改进建议
- Then ≥ 8 份建议为"具体可操作"（非空话）

- Given Phase 0.2 真实样本（2-3 段真人录音）
- When 跑同一套评估流程
- Then 评估结果合理（评分分布正常、评语引用客观指标）

**Gate**：所有 6 条 AC 通过 → Phase 0 PASS → 进入 MVP 实现
**Related Requirements**: Section 11 Phase 0 POC Gate
**RICE**: Impact=5, Effort=2, Score=2.5（高回报风险缓释）

---

# Epic 1: 完成一场模拟面试

覆盖用户从进入平台到完成一场面试的完整旅程。

## US-001 [M] 配置面试参数

**As a** 学生求职者（林可）
**I want** 在开始面试前选择目标公司、岗位、语言和时长
**So that** 面试体验与我的实际求职目标匹配

**Acceptance Criteria**

- Given 用户打开首页并点击"开始模拟面试"
- When 进入设置页面
- Then 展示可选项：公司（内置列表 + 上传）、岗位输入框、语言（中/英）、时长（默认 45-60 分钟 / 8-15 题，可自定义）

- Given 用户填写完必填项
- When 点击"开始面试"
- Then 进入面试页并自动触发麦克风权限请求

- Given 用户未选公司或岗位为空
- When 点击"开始面试"
- Then 表单显示校验错误，不允许进入下一步

**Related FR**: FR-1.1
**RICE**: Impact=5, Effort=2, Score=2.5

---

## US-002 [S] 选择内置公司面试风格

**As a** 学生求职者
**I want** 从内置的公司列表（字节、Amazon、腾讯等）中选择目标公司
**So that** 不用自己准备风格文档就能获得定制化面试

**Acceptance Criteria**

- Given 用户在设置页
- When 点击"选择公司"下拉框
- Then 看到至少 2-3 家内置公司 + 每家有简短风格描述（如"字节：高压提问，注重业务思考"）

- Given 用户选中某家公司
- When 确认选择
- Then 该公司的 interviewer style + sample questions + prompt context 在面试时传给 Claude

**Related FR**: FR-1.2
**RICE**: Impact=4, Effort=2, Score=2

---

## US-003 [S] 上传自定义公司风格文档

**As a** 学生求职者
**I want** 上传自己整理的目标公司面试风格文档
**So that** 对于内置列表没有的公司也能定制面试体验

**Acceptance Criteria**

- Given 用户在设置页点击"上传自定义风格"
- When 选择一份 Markdown 或 .txt 文件（≤ 50KB）
- Then 文件被解析并作为本次面试的 Claude context

- Given 用户上传超过 50KB 的文件
- When 提交
- Then 显示"文件过大"错误并拒绝

- Given 用户上传非支持格式
- When 提交
- Then 显示"仅支持 .md 或 .txt"错误

**Related FR**: FR-1.3
**RICE**: Impact=3, Effort=1, Score=3

---

## US-004 [M] 上传简历 / JD 作为面试上下文

**As a** 学生求职者
**I want** 可选上传我的简历或目标岗位 JD
**So that** AI 面试官能基于我的背景提问，提升针对性

**Acceptance Criteria**

- Given 用户在设置页
- When 点击"上传简历/JD"并选择 PDF 或文本文件
- Then 文件内容被提取并作为 Claude context（仅本次面试使用，不持久化）

- Given 面试开始
- When Claude 生成第一题
- Then 问题中包含基于简历的针对性提问（可通过 prompt 设计实现）

- Given 用户跳过此步骤
- When 开始面试
- Then 使用泛用问题生成（不影响流程）

**Related FR**: FR-1.1 (简历上传部分), FR-2.3
**RICE**: Impact=5, Effort=2, Score=2.5

---

## US-005 [M] 进行端到端语音面试

**As a** 学生求职者
**I want** 像真实面试一样用语音与 AI 面试官对话
**So that** 获得沉浸式练习体验，锻炼语音表达能力

**Acceptance Criteria**

- Given 用户已进入面试页且麦克风权限授予
- When 点击"开始"
- Then AI 在 1.5 秒内用语音打招呼并介绍规则

- Given AI 提问结束
- When 用户用语音回答
- Then 语音通过 WebSocket 实时传给后端，后端转码为 LPCM 16kHz 后送 Nova Sonic

- Given 用户说完话 1 秒无新输入
- When Nova Sonic 检测到语音结束
- Then AI 在 1.5 秒内开始下一个问题或追问

- Given 用户的麦克风被系统静音
- When 面试开始
- Then 前端检测到无音频流并提示"请检查麦克风"

**Related FR**: FR-2.1
**RICE**: Impact=5, Effort=5, Score=1 （核心功能，最复杂）

---

## US-006 [M] 面试中查看进度和实时反馈

**As a** 学生求职者
**I want** 在面试进行中看到当前进度、AI/自己的说话状态和转录
**So that** 保持对面试节奏的掌控，减少焦虑

**Acceptance Criteria**

- Given 面试进行中
- When 当前正在进行第 N 题
- Then 页面展示"第 N / 总题数"、大致剩余时间、音波可视化（Framer Motion）

- Given AI 正在说话
- When 用户看屏幕
- Then 有清晰的视觉指示（如"AI 正在提问..."+ 动画）

- Given 用户正在说话
- When 实时转录从后端返回
- Then 转录文字以 subtle 样式（小号、半透明）显示在屏幕下方，不抢焦点

**Related FR**: FR-2.4
**RICE**: Impact=4, Effort=3, Score=1.3

---

## US-007 [M] 严格模式下完成整场面试

**As a** 学生求职者
**I want** 严格模式不允许暂停，模拟真实面试压力
**So that** 练习效果更接近真实场景

**Acceptance Criteria**

- Given 面试开始后
- When 用户尝试刷新、关闭标签页、或按 ESC
- Then 浏览器弹出"确认离开吗？离开将放弃本场面试"的警告

- Given 用户确认离开
- When 页面关闭
- Then 后端 WebSocket 断开 10 秒内将 interview.status 设为 `abandoned`

- Given 面试正常完成所有题目
- When AI 说"面试结束"
- Then interview.status = `completed` 并跳转至"正在生成报告..."页面

**Related FR**: FR-2.2
**RICE**: Impact=3, Effort=1, Score=3

---

## US-008 [M] 动态问题生成与追问

**As a** 学生求职者
**I want** AI 基于我的回答动态追问和生成后续问题
**So that** 面试体验真实，不是脚本化问答

**Acceptance Criteria**

- Given 用户已回答第 N 题
- When 回答内容不完整（如缺少"结果"环节的 STAR 故事）
- Then AI 有 ≥ 30% 概率触发追问（prompt 中定义的策略）

- Given 用户的回答涉及具体项目 / 简历内容
- When Claude 生成下一题
- Then 下一题可以深挖该项目细节（展示上下文感知能力）

- Given 已完成 N 题，N < 目标题数
- When Claude 基于 context 生成下一题
- Then 新题与已问过的题不重复，风格符合所选公司

**Related FR**: FR-2.3
**RICE**: Impact=5, Effort=4, Score=1.25

---

## US-009 [M] 错误场景下的清晰反馈（麦克风 / 网络 / 服务）

**As a** 学生求职者
**I want** 遇到技术问题时看到清晰的错误提示和下一步指引
**So that** 不会因为技术卡顿而挫败放弃

**Acceptance Criteria**

- Given 用户首次进入面试页
- When 麦克风权限被拒绝
- Then 显示"需要麦克风权限 + 如何在浏览器设置中开启"的图文引导

- Given 面试进行中网络中断
- When 前端检测到 WebSocket 断开且 10 秒未恢复
- Then 显示"网络异常，面试终止，已采集数据已保存"并跳回首页

- Given 面试开始前 Bedrock Nova Sonic 不可用
- When 尝试建立 WebSocket
- Then 显示"AI 服务暂不可用，请稍后再试"并不扣用户"面试次数"（MVP 无此概念，但语义保留）

- Given 浏览器不支持 MediaRecorder / WebRTC
- When 用户访问面试页
- Then 显示"请使用 Chrome 90+ 或 Safari 16+"

**Related FR**: FR-6.1, FR-6.2, FR-6.3
**RICE**: Impact=4, Effort=2, Score=2

---

# Epic 2: 查看和管理历史记录

## US-010 [M] 查看面试记录列表

**As a** 学生求职者
**I want** 查看所有历史面试记录的列表
**So that** 追踪自己的练习和进步

**Acceptance Criteria**

- Given 用户在首页
- When 点击"我的面试记录"
- Then 进入列表页，按时间倒序展示所有记录

- Given 每条记录
- When 用户浏览列表
- Then 卡片显示：日期时间、公司、岗位、总分（若已评估）、状态（completed / evaluation_failed / abandoned）

- Given 列表超过 20 条
- When 用户滚动
- Then 分页或无限滚动加载更多

- Given 没有任何历史记录
- When 首次访问列表
- Then 显示空状态插图 + "还没有练习记录，开始第一场面试"按钮

**Related FR**: FR-4.1
**RICE**: Impact=4, Effort=2, Score=2

---

## US-011 [M] 查看面试详情与音频回放

**As a** 学生求职者
**I want** 点击某条面试记录，看到完整的评估报告和按段落播放的音频
**So that** 复盘每道题的表现，针对性提升

**Acceptance Criteria**

- Given 用户点击某条 `completed` 状态的记录
- When 详情页加载
- Then 首屏 2 秒内展示完整评估报告（整体评分 + 三维雷达图 + 每题分析）

- Given 详情页展示每题的用户回答转录
- When 用户点击某一段转录文字
- Then 对应音频片段从该段开始播放（使用 S3 pre-signed URL）

- Given 记录状态为 `abandoned`
- When 查看详情
- Then 显示"未完成"标识 + 已采集的部分问答（无评估报告）

- Given 记录状态为 `evaluation_failed`
- When 查看详情
- Then 显示"报告生成失败"+ "重试生成"按钮

**Related FR**: FR-4.2, FR-3.2 (ACrit 3)
**RICE**: Impact=5, Effort=3, Score=1.67

---

## US-012 [S] 导出面试报告为 PDF

**As a** 学生求职者
**I want** 将某次面试的评估报告导出为 PDF
**So that** 离线复习或分享给老师/师兄师姐得到建议

**Acceptance Criteria**

- Given 用户在面试详情页
- When 点击"导出 PDF"
- Then 后台生成包含元数据、问题、转录、评估、改进建议、理想范答的 PDF 文件

- Given PDF 生成完成
- When 用户点击下载
- Then 浏览器下载 PDF，命名格式：`面试_<公司>_<岗位>_<日期>.pdf`

- Given PDF 生成失败
- When 用户点击导出
- Then 显示错误并允许重试

**Related FR**: FR-4.3 (PDF 部分)
**RICE**: Impact=3, Effort=2, Score=1.5

---

## US-013 [S] 下载原始音频

**As a** 学生求职者
**I want** 下载某次面试的原始音频文件
**So that** 自己反复听，发现语音问题

**Acceptance Criteria**

- Given 用户在详情页
- When 点击"下载音频"
- Then 浏览器通过 S3 pre-signed URL 下载用户回答音频（合并后的完整文件）

- Given 音频文件不存在（如 abandoned 早期状态）
- When 点击下载
- Then 下载按钮禁用或显示"无可下载内容"

**Related FR**: FR-4.3 (音频部分)
**RICE**: Impact=2, Effort=1, Score=2

---

## US-014 [S] 删除面试记录

**As a** 学生求职者
**I want** 删除不想保留的面试记录
**So that** 管理自己的历史数据，保护隐私

**Acceptance Criteria**

- Given 用户在列表页或详情页
- When 点击"删除"
- Then 弹出确认对话框（强调"此操作不可撤销"）

- Given 用户确认删除
- When 后端处理
- Then 数据库记录删除 + S3 上对应音频文件删除 + 列表刷新

- Given 删除失败（如 S3 错误）
- When 后端返回错误
- Then 前端回滚显示 + 提示用户重试

**Related FR**: FR-4.4
**RICE**: Impact=2, Effort=1, Score=2

---

# Epic 3: 理解我的面试表现

## US-015 [M] 获取三维评分与整体评估

**As a** 学生求职者
**I want** 面试结束后看到内容/表达/语音三维评分和整体分析
**So that** 快速了解自己的强弱项

**Acceptance Criteria**

- Given 面试结束
- When 评估报告生成完成
- Then 整体评估包含：总分（0-100）、三维雷达图（内容/表达/语音各 0-100）、总体评语文本、改进优先级列表

- Given 评估报告展示
- When 用户查看
- Then 三维雷达图使用 Framer Motion / Tremor 动画呈现分数上升效果

- Given 评估维度包含语音维度
- When Claude 生成评估
- Then 评估基于音频转录 + 时长数据（语速可计算）+ 停顿数据（基于 Nova Sonic 的 silence detection）

**Related FR**: FR-3.1, FR-3.2
**RICE**: Impact=5, Effort=3, Score=1.67

---

## US-016 [M] 获取每题改进建议与理想范答

**As a** 学生求职者
**I want** 每道题看到我的回答问题点 + 具体改进建议 + Claude 生成的理想范答
**So that** 知道下次怎么回答更好

**Acceptance Criteria**

- Given 评估报告已生成
- When 用户展开某一题
- Then 看到：原问题、我的回答转录、三维评分、3-5 条具体改进建议、1 段理想范答

- Given 改进建议
- When Claude 生成
- Then 建议必须具体、可操作（如"在第二段加入定量数据"而非"回答更好"）

- Given 理想范答
- When 展示
- Then 标注为"参考答案"（非唯一正解），风格与所选公司匹配

**Related FR**: FR-3.2
**RICE**: Impact=5, Effort=3, Score=1.67

---

## US-017 [M] 评估异步生成的用户等待体验

**As a** 学生求职者
**I want** 面试结束后清楚知道评估生成进度
**So that** 不会因为等待而焦虑或以为系统卡了

**Acceptance Criteria**

- Given 面试结束
- When 用户被跳转至等待页
- Then 显示"正在生成评估报告..."+ 预计时间（"约 55 秒"）+ 动画

- Given 评估生成完成
- When 后端通知前端（轮询或 WebSocket）
- Then 自动跳转到详情页

- Given 评估生成超过 60 秒
- When 前端检测超时
- Then 显示"报告仍在生成，稍后在记录列表查看"，用户可返回首页

- Given 评估失败（Claude 调用失败 2 次重试均失败）
- When 前端收到失败通知
- Then 显示"生成失败，点击重试"+ 记录标记 `evaluation_failed`

**Related FR**: FR-3.3, FR-6.3
**RICE**: Impact=4, Effort=2, Score=2

---

# Traceability: Stories → Functional Requirements

| Story | Related FR | Priority |
|---|---|---|
| US-000 | Section 11 (Phase 0 POC Gate) | M |
| US-001 | FR-1.1 | M |
| US-002 | FR-1.2 | S |
| US-003 | FR-1.3 | S |
| US-004 | FR-1.1 (简历), FR-2.3 | M |
| US-005 | FR-2.1 | M |
| US-006 | FR-2.4 | M |
| US-007 | FR-2.2 | M |
| US-008 | FR-2.3 | M |
| US-009 | FR-6.1/6.2/6.3 | M |
| US-010 | FR-4.1 | M |
| US-011 | FR-4.2 | M |
| US-012 | FR-4.3 (PDF) | S |
| US-013 | FR-4.3 (音频) | S |
| US-014 | FR-4.4 | S |
| US-015 | FR-3.1, FR-3.2 | M |
| US-016 | FR-3.2 | M |
| US-017 | FR-3.3, FR-6.3 | M |

**Coverage**: 所有 MVP FR（FR-1.1 ~ FR-4.4 + FR-6.*）均至少被一个 story 覆盖。

---

# Persona → Stories Mapping

| Persona | Stories | 覆盖度 |
|---|---|---|
| 林可（学生求职者，primary） | US-001 ~ US-017（全部） | 100% |
| 陈老师（管理员，secondary） | — (Beta 阶段) | 0% (MVP) |

---

# Story Statistics

- **Total Stories**: 18 (含 Phase 0)
- **Must [M]**: 12 (US-000 + 11 MVP Must)
- **Should [S]**: 6
- **Could [C]**: 0
- **Phase 分布**:
  - Phase 0 POC: 1 story (US-000)
  - Phase 1 MVP: 17 stories (US-001 ~ US-017)
- **Epic Breakdown** (MVP):
  - Epic 1 (完成一场面试): 9 stories
  - Epic 2 (历史记录管理): 5 stories
  - Epic 3 (理解表现): 3 stories

# Delivery Sequence

**Phase 0**（~2-3 天）：POC 验证评估算法 → 必须 PASS 才进入 MVP
**Phase 1 MVP**：11 Must stories（US-001 ~ US-011, US-015 ~ US-017 中的 Must）
**Phase 1 MVP v1.1**：6 Should stories（快速迭代）
