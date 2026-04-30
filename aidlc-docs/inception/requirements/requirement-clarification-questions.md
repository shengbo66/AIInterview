# Requirements Clarification Questions

我在你的回答中发现**几处矛盾和歧义**，需要澄清后才能生成准确的 requirements。请在每题 `[Answer]:` 后填写字母，全部答完回复 "done"。

---

## 矛盾 1：MVP 范围 vs 管理后台 vs 认证系统

**原始回答**：
- Q15: 从 MVP 开始，稳定后迭代到 Beta
- Q17: 预算不敏感，追求最佳体验
- Q18: 需要完整管理后台，查看所有用户面试记录
- Q8: 部署前不需要认证（本地功能验证前）

**矛盾点**：没有认证就没有"用户"概念，也就没有"管理员查看其他用户记录"的场景。完整管理后台又通常不是 MVP 的范围。

### Clarification 1.1

**MVP 阶段**（本地功能验证）的范围应该是？

A) 只做核心面试流程（语音面试 + AI 评估 + 单人面试记录查看），**不含任何认证和管理后台**
B) 核心面试流程 + 本地单用户记录列表（无认证，默认就是自己），但**管理后台留到 Beta 阶段**
C) 核心面试流程 + 简单认证（Cognito） + 管理后台一并做完
D) Other (please describe)

[Answer]: A (accepted recommendation)

### Clarification 1.2

**管理后台**的优先级？

A) 必须在 MVP 一并实现（你一个人用，但想先验证管理功能）
B) 在 Beta 阶段加入（MVP 验证完主流程后再做）
C) 做最小版本（能列出所有面试、点进去看详情即可，其他统计/题库管理后续再加）
D) Other (please describe)

[Answer]: B (accepted recommendation)

---

## 矛盾 2：SQLite + 小规模 vs AWS 部署 + 管理后台

**原始回答**：
- Q11: AWS 部署
- Q14: SQLite + S3（你在 chat 里说）
- Q16: 1-10 人并发
- Q18: 完整管理后台（需要跨用户查询）

**矛盾点**：SQLite 是单文件数据库，AWS 部署时可以塞进一个 ECS/App Runner 容器（挂载 EBS 或用 Litestream 备份到 S3），但**如果迭代到 Beta 有多用户 + 管理后台跨用户查询**，SQLite 的并发写入会有瓶颈。

### Clarification 2.1

关于存储演进路径，你倾向于？

A) **MVP 用 SQLite**（极简部署，单容器），**Beta 阶段迁移到 PostgreSQL**（我会在 requirements 里明确标注迁移时机和数据迁移方案）
B) **直接用 PostgreSQL**（Aurora Serverless v2 最低档 ~$40/月或 RDS t4g.micro ~$15/月，一步到位不用迁移）
C) **SQLite 一直用下去**（反正规模小，不考虑迁移）
D) Other (please describe)

[Answer]: A (accepted recommendation)

---

## 矛盾 3：纯语音交互 vs 面试前设置

**原始回答**：
- Q19: 纯语音（面试全程无打字）
- Q4: 用户可导入外部公司面试风格要求

### Clarification 3.1

**面试前的设置阶段**（选公司/岗位、导入 JD、选语言等）如何进行？

A) **面试前是图形界面**（下拉选公司、上传 JD 文件、选语言），**面试中是纯语音**
B) 全程语音引导（包括设置阶段 AI 用语音问你"要面试哪家公司？"）
C) Other (please describe)

[Answer]: A (accepted recommendation)

---

## 矛盾 4：严格+宽松两种模式 vs MVP

**原始回答**：
- Q20: 严格模式 + 宽松模式两种选择
- Q15: MVP 优先

### Clarification 4.1

面试暂停/中断功能的优先级？

A) **MVP 只做严格模式**（一旦开始必须完成，不允许暂停；Beta 再加宽松模式）
B) **MVP 只做宽松模式**（可随时暂停保留进度；体验更友好，先跑通）
C) **MVP 就做两种模式**（虽然工作量大但都做了）
D) Other (please describe)

[Answer]: A (accepted recommendation)

---

## 歧义 1：公司面试风格数据来源

**原始回答**（Q4）：
> 需要在网络上，按照模拟的公司，根据该公司的面试风格进行定制。比如华为，比如 TCL，美的等。可以从外部导入该公司的面试风格要求

**歧义点**："从外部导入"具体指什么？

### Clarification 5.1

**公司面试风格数据**的来源是？

A) **用户手动上传**：用户自己准备一份 markdown/PDF 文件（含公司面试风格描述、常见题目），上传到系统后作为 Claude 的 context
B) **系统内置题库**：我们预先准备少量头部公司（华为、TCL、美的、字节、腾讯等）的面试风格描述，打包在系统里，用户选择即可
C) **A + B**：内置 5-10 家常见公司的风格，用户也可上传自己整理的风格文档
D) **AI 实时搜索**：Claude 基于公司名称和岗位，自己推理出面试风格（不依赖本地数据）
E) Other (please describe)

[Answer]: C (accepted recommendation)

### Clarification 5.2

**公司面试风格**的内容格式建议？（会影响数据模型设计）

A) 结构化字段：公司名 + 面试官风格（严谨/友好/压力） + 偏好题型 + 常见题目列表
B) 非结构化：一段纯文本描述，直接作为 Claude 的 prompt context
C) A + B 都支持：结构化字段 + 补充说明文本
D) 由 AI 推荐格式
E) Other (please describe)

[Answer]: C (accepted recommendation)

---

## 歧义 2：中英双语切换粒度

### Clarification 6.1

**中英双语**的切换单位？

A) **整场面试一种语言**：开始前选中文或英文，整场都是这种语言（最简单）
B) **问答级别可切换**：用户某一题可用中文答，下一题用英文答（AI 跟随）
C) **UI 语言 + 面试语言独立**：UI 可以是中文，面试内容可以是英文（外企面试常见场景）
D) Other (please describe)

[Answer]: A (accepted recommendation)

---

## 补充 1：面试类型范围界定（基于你选的 E "全部"）

### Clarification 7.1

你选了 Q2 的 E（所有面试类型都支持）。在 **MVP 阶段**，优先实现哪些？

A) **全部同时支持**（技术 + 行为 + 综合 + 专业领域）——工作量大但完整
B) **先支持行为面试 + 综合素质**（最通用、对所有岗位都适用、不依赖编程环境）
C) **先支持行为面试**（最容易验证 AI 评估效果，再扩展其他）
D) Other (please describe)

[Answer]: B (accepted recommendation)

**补充说明**：技术面试涉及"用户现场编写代码"的交互（需要代码编辑器、运行时等），远比行为/综合面试复杂。

---

## 补充 2：音频记录的回放体验

### Clarification 8.1

**面试记录详情页**的回放体验？

A) 只有**文字转录**，按时间顺序展示（问题 → 回答文字 → AI 评价）
B) **文字 + 可点击片段播放音频**（点每段文字播放对应音频片段，像播客 chapter）
C) **完整音频播放器 + 同步高亮文字**（像字幕效果，播放到哪里文字高亮到哪里）
D) Other (please describe)

[Answer]: B (accepted recommendation)

---

填完所有问题后回复 "done"。
