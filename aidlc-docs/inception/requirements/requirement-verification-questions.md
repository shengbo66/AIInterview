# Requirements Verification Questions — Mock Interview Platform

请在每题的 `[Answer]:` 后填入字母选项（A/B/C/D/E/...），如需补充说明请在字母后加冒号描述。若选项都不合适，选择最后一项 "Other" 并描述。全部答完后告诉我 "done"。

---

## Part 1: 目标用户与使用场景

### Question 1

这个平台的**主要目标用户**是谁？

A) 求职者（准备找工作的人，练习通用面试技能）
B) 在校学生（校招准备，技术面试练习）
C) 职场人士（跳槽准备，资深岗位面试）
D) 以上全部（通用面试练习平台）
E) 企业 HR / 招聘方（用于培训面试官，也可用于候选人筛选）
F) Other (please describe after [Answer]: tag below)

[Answer]: B

### Question 2

**面试类型**主要覆盖哪些？（多选可用 A+B 形式）

A) 技术面试（编程、算法、系统设计）
B) 行为面试（Behavioral / STAR 故事）
C) 综合素质面试（通用沟通、逻辑、表达）
D) 专业领域面试（产品、市场、财务等 role-specific）
E) 以上全部，用户可选择类型
F) Other (please describe after [Answer]: tag below)

[Answer]: E

### Question 3

是否需要支持**多语言**面试？

A) 只需中文
B) 只需英文
C) 中英双语（用户可切换）
D) 多语言（包含日/韩/其他）
E) Other (please describe after [Answer]: tag below)

[Answer]: C

---

## Part 2: 核心功能细节

### Question 4

面试问题的**来源**是什么？

A) 完全由 Claude Sonnet 动态生成（基于岗位/简历上下文）
B) 预置题库 + Claude 动态补充
C) 用户可上传 JD（职位描述）/ 简历，Claude 基于此生成针对性问题
D) 以上组合：预置题库 + JD/简历上传 + 动态生成
E) Other (please describe after [Answer]: tag below)

[Answer]: 需要在网络上，按照模拟的公司，根据该公司的面试风格进行定制。比如某公司，比如 TCL，美的等。可以从外部导入该公司的面试风格要求；

### Question 5

单次面试的**时长与题目数量**？

A) 短面（10-15 分钟，3-5 题）
B) 中等（20-30 分钟，5-8 题）
C) 长面（45-60 分钟，8-15 题）
D) 用户自定义
E) Other (please describe after [Answer]: tag below)

[Answer]: 缺省 C，可以 D

### Question 6

**评估维度**需要覆盖哪些？

A) 回答内容准确性 + 完整性
B) A + 沟通表达（逻辑、清晰度、结构化）
C) B + 语音维度（语速、停顿、流畅度、情感）
D) C + 非语言维度（未来可扩展：表情、姿态，如果有视频）
E) Other (please describe after [Answer]: tag below)

[Answer]: C

### Question 7

**改进建议**的粒度？

A) 只在面试结束后给整体建议 + 每题改进建议
B) A + 每题提供"理想范答"（由 Claude 生成的参考答案）
C) B + 实时/渐进式提示（面试中可选择是否启用提示）
D) Other (please describe after [Answer]: tag below)

[Answer]: B

---

## Part 3: 用户身份与数据

### Question 8

**用户身份系统**？

A) 无需登录，匿名使用（本地保存，或按 session 使用）
B) 简单邮箱注册 + 密码
C) 社交登录（Google / GitHub / 微信等 OAuth）
D) B + C 都支持
E) 企业 SSO（面向 B2B 场景）
F) Other (please describe after [Answer]: tag below)

[Answer]: Cognito；部署阶段再考虑。完成本地功能验证前不需要考虑；

### Question 9

**面试记录**的存储与查看？

A) 只保存评估结果 + 文字转录（text transcript）
B) A + 保存完整音频录音（可回放）
C) B + 支持导出（PDF 报告 / 音频文件下载）
D) C + 支持分享链接（给教练/朋友查看）
E) Other (please describe after [Answer]: tag below)

[Answer]: C，并且管理员可以支持查看所有用户记录。

### Question 10

**数据隐私**要求？

A) 基础：HTTPS + 加密存储，用户可删除自己的记录
B) A + 符合 GDPR / 国内数据合规
C) A + 录音在评估后自动删除（只留文字转录）
D) Other (please describe after [Answer]: tag below)

[Answer]: A

---

## Part 4: 部署与技术栈

### Question 11

**部署目标**？

A) AWS 云（充分利用 Bedrock Nova Sonic + Claude）
B) 本地 / 私有化部署
C) 混合（前端在 AWS，后端可本地）
D) Other (please describe after [Answer]: tag below)

[Answer]: A

### Question 12

**前端 UI 技术栈偏好**？（"社区最新 UI 技术"需要明确方向）

A) Next.js 15 (App Router) + React 19 + Tailwind CSS + shadcn/ui（当前最主流的"时尚"组合）
B) Next.js + Tailwind + Radix UI + Framer Motion（强动效，现代感）
C) Vite + React + Tailwind + shadcn/ui（轻量 SPA）
D) SvelteKit / Solid / Qwik（更前沿，但社区生态较小）
E) 由 AI 推荐最合适的（基于"时尚 + 吸引面试者"这一目标）
F) Other (please describe after [Answer]: tag below)

[Answer]: 

### Question 13

**后端技术栈偏好**？

A) Python (FastAPI) — 与 AI/Bedrock SDK 生态契合
B) Node.js (TypeScript, Nest.js 或 Hono) — 与前端同语言
C) Python FastAPI + Node.js BFF（前端专用后端）
D) Serverless（AWS Lambda + API Gateway）
E) 由 AI 推荐
F) Other (please describe after [Answer]: tag below)

[Answer]: 

### Question 14

**存储层**偏好？

A) PostgreSQL（关系型，强一致）+ S3（音频文件）
B) DynamoDB（serverless 友好）+ S3
C) SQLite（本地 / MVP 阶段）+ 本地文件
D) 由 AI 推荐
E) Other (please describe after [Answer]: tag below)

[Answer]: 

---

## Part 5: 非功能性需求与范围

### Question 15

**项目当前阶段**？

A) MVP（最小可用，优先核心流程跑通，UI 精美但功能精简）
B) Beta（核心功能 + 一定范围用户测试，需要身份系统 + 数据持久化）
C) 生产级（完整功能 + 高可用 + 监控 + 合规）
D) Other (please describe after [Answer]: tag below)

[Answer]: 从 A 开始，稳定后迭代到 B

### Question 16

**并发用户预期**？

A) 个人使用 / 极小规模（1-10 人，本地或小型部署）
B) 小规模（100 以内同时在线）
C) 中等规模（1000+ 同时在线）
D) 不确定 / 暂不考虑（按 MVP 处理）
E) Other (please describe after [Answer]: tag below)

[Answer]: A

### Question 17

**预算与成本敏感度**？（影响 Bedrock 调用频率、模型选择、实例规格）

A) 成本敏感（MVP 阶段，尽量控制 AWS 花费，可用更便宜的模型替代）
B) 平衡（核心体验用 Nova Sonic + Claude Sonnet，非核心用轻量模型）
C) 不敏感（追求最佳体验，预算充足）
D) Other (please describe after [Answer]: tag below)

[Answer]: C

### Question 18

是否需要**管理后台**（查看所有用户、题库管理、使用统计）？

A) 不需要（MVP 阶段只做用户端）
B) 简易版（只看统计 + 题库管理）
C) 完整管理后台
D) Other (please describe after [Answer]: tag below)

[Answer]: C，需要查询所有用户的面试记录

---

## Part 6: 交互细节

### Question 19

**语音交互模式**（Nova Sonic 支持端到端语音）？

A) 纯语音（用户说，AI 说，全程无打字）
B) 语音为主，支持打字切换（用户可选择说或打）
C) 文字为主，可选语音输入（语音是加分项）
D) Other (please describe after [Answer]: tag below)

[Answer]: A。但是查看面试记录可以支持语音+文字记录

### Question 20

**面试中能否暂停/中断/重来**？

A) 可随时暂停，保留进度继续
B) 可中断，但中断后不保存（需要重新开始）
C) 严格模式（真实面试体验，不允许暂停）+ 宽松模式（可暂停）两种选择
D) Other (please describe after [Answer]: tag below)

[Answer]: C

---

## 说明：选项 E (Other)

如果你的答案不在列出的选项里，请写：

```
[Answer]: E: [你的描述]
```

填完所有问题后回复 "done" 或 "完成"，我会读取并生成完整的 requirements 文档。
