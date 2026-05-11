# TCL Embodied AI Architect L2 — Mock 面试场景设计

**日期**: 2026-05-11  
**状态**: 已批准，待实施  
**方案**: A（复用 CompanyStyle 表，最小改动）

---

## 背景与目标

在现有"某公司（硬件射频实习）"面试场景基础上，新增 TCL Embodied AI Architect L2 Mock 面试场景。两个场景在前端以卡片形式并存，用户选择后开始面试。现有某公司流程完全不受影响。

**参考资料**：
- TCL 企业文化：四大核心价值观（变革/创新/责任/卓越）、五大核心能力素质（学习力/执行力/规划力/沟通力/管控力）、三轮面试体系（L1/L2/M1）
- 目标岗位：TCL EL Shanghai，Embodied AI Architect，R&D Technology，JD 职责模块：System Architecture(50%)、Integration & Optimization(25%)、Collaboration(15%)、Strategic Input(10%)

---

## 数据库变更（一次 Alembic Migration）

新增两列：

### `company_style.rubric_type VARCHAR(20)`
- `"faang"` — 某公司（默认，向后兼容）
- `"tcl_l2"` — TCL Embodied AI Architect L2
- 用于 `evaluation_service.py` dispatch，替代魔法字符串比较

### `evaluation.dimension_scores JSON`
- 存各维度原始分，供前端详情页渲染
- 某公司：`{"content": 80, "expression": 70, "voice": 65}`（聚合值，与现有三列冗余）
- TCL：`{"tech_depth": 82, "architecture": 75, "competency": 70, "culture": 85, "voice": 60}`
- 现有 `content_score / expression_score / voice_score` 三列保留为展示聚合值，计算逻辑不变

---

## 后端数据层

### 新增 `backend/app/seed/tcl_style.py`

与 `company_styles.py` 结构完全对称：

```python
COMPANY_STYLE = {
    "name": "TCL",
    "rubric_type": "tcl_l2",
    "interviewer_style_tags": [
        "技术深度优先",
        "STAR 行为面试",
        "系统架构能力",
        "TCL五大能力素质",
        "变革创新文化",
    ],
    "preferred_question_types": [
        "具身AI/机器人系统架构设计",
        "ML框架与工程实践（PyTorch/C++）",
        "硬件-AI-云端集成方案",
        "STAR行为题（五大能力素质）",
        "TCL文化价值观匹配",
    ],
    "sample_questions": [
        # 技术深度
        "请描述你设计过的一个具身 AI 系统的端到端软件架构，重点说明各模块的接口定义和数据流。",
        "在机器人感知-规划-执行链路中，你如何处理传感器数据延迟和不确定性？",
        "请对比 ROS2 和自研 middleware 在家庭机器人场景下的 trade-off。",
        "你如何设计一个支持 VLM 推理的实时感知模块？对算力/延迟/精度如何做 trade-off？",
        # 系统架构与集成
        "描述一次你将 AI 算法模块与嵌入式硬件集成的经历，遇到了哪些接口和性能问题？",
        "你如何在边端（嵌入式）和云端之间做推理任务的分配决策？",
        # STAR 行为题（TCL 五大能力素质）
        "举一个你主导了复杂系统架构决策的案例，从方案选型到落地的完整过程。（规划力/执行力）",
        "描述一次你在跨团队（硬件/算法/产品）协作中化解技术分歧的经历。（沟通力）",
        "讲一个你在模糊需求下独立推进并交付的项目。（学习力/管控力）",
        # 文化契合
        "TCL 强调在快节奏模糊环境中独立工作。请举例说明你是如何在不确定环境下做出关键决策的。",
    ],
    "prompt_context_text": (
        "TCL L2 技术面试评估体系围绕五大维度展开：\n"
        "1. 技术深度（35%）：具身AI/机器人架构知识、ML框架(PyTorch/TensorFlow)和"
        "编程语言(C++/Python)熟练度、系统调试与优化能力；\n"
        "2. 系统架构（25%）：端到端架构设计能力、硬件/AI算法/云服务无缝集成方案、"
        "接口定义与协议设计；\n"
        "3. TCL五大能力素质（20%）：用STAR方法考察学习力、执行力、规划力、沟通力、管控力；\n"
        "4. 文化契合（10%）：变革（Change）、创新（Innovation）、责任（Responsibility）、"
        "卓越（Excellence）四大核心价值观；\n"
        "5. 语音表现（10%）：客观语音指标（语速/停顿/口头禅/情感倾向）。\n\n"
        "面试风格：\n"
        "- L2 技术深度面：追问到参数/数据/设计决策级别，不接受泛泛而谈；\n"
        "- STAR 结构是行为题的核心工具，要求 Situation/Task/Action/Result 四要素完整；\n"
        "- 重视候选人在模糊/快节奏环境下的独立判断能力；\n"
        "- 鼓励展示系统性思维和 trade-off 分析，而非单一答案。\n\n"
        "岗位背景（Embodied AI Architect，TCL EL Shanghai）：\n"
        "- 设计家庭机器人具身 AI 端到端软件架构；\n"
        "- 管理传感器/摄像头数据，指导 middleware/仿真/工具选型；\n"
        "- 确保硬件/AI算法/云服务的无缝集成；\n"
        "- 与感知/规划/HRI/情感智能研究团队协作。\n\n"
        "加分项：VLM、多模态学习、VLA系统经验；Android OS 和嵌入式实时系统深度理解。"
    ),
}
```

`seed_if_empty(session)` 按 `name="TCL"` 查重后插入，重复调用幂等。

### 修改 `backend/app/main.py`

startup 顺序调用：
```python
await company_styles.seed_if_empty(db)   # 某公司（rubric_type="faang"）
await tcl_style.seed_if_empty(db)        # TCL（rubric_type="tcl_l2"）
```

### 修改 `BidiInterviewSession`

`__init__` 新增参数：
- `company_style_id: str | None = None`
- `language: str = "zh"`

`_load_company_style()` 逻辑：
- `company_style_id` 非 None → 按 id 查询（不存在则 raise）
- `company_style_id` 为 None → fallback 取 `name="某公司"` 的记录（不再依赖顺序）

`Interview` 创建时写入 `language` 字段。

### 修改 `backend/app/routers/demo_bidi.py`

WebSocket endpoint 从 query params 读取：
```
ws://host/ws/interview-demo?token=...&style_id=<uuid>&lang=zh|en
```
- `style_id` 缺失 → 传 `None`（触发 fallback）
- `lang` 缺失 → 默认 `"zh"`
- 后端验证 `style_id` 存在于 DB，不存在返回 4008 close code

---

## 评分引擎

### 新增 `shared/eval_core/tcl_rubric.py`

```python
TCL_L2_CHECKPOINTS = [
    ("tech_depth_knowledge", "Technical Domain Knowledge",
     "具身AI/机器人架构/感知规划/HRI/VLM知识深度"),
    ("tech_depth_impl",      "Implementation Proficiency",
     "ML框架(PyTorch/TF)、C++/Python、系统调试与优化能力"),
    ("arch_e2e_design",      "E2E Architecture Design",
     "端到端软件架构设计能力与接口/协议定义"),
    ("arch_integration",     "HW/AI/Cloud Integration",
     "硬件、AI算法、云端集成方案的合理性与完整性"),
    ("tcl_competency_star",  "TCL Five Competencies (STAR)",
     "STAR结构展现学习力/执行力/规划力/沟通力/管控力"),
    ("tcl_culture_fit",      "TCL Culture Alignment",
     "变革/创新/责任/卓越价值观契合度，在模糊环境独立工作能力"),
]

# 映射到 DB 聚合列的权重
TCL_TO_DB_WEIGHTS = {
    "content_score":    # tech_depth(35%) + arch(25%) → 归一化到 0-100
    "expression_score": # competency(20%) + culture(10%) → 归一化到 0-100
    "voice_score":      # 沿用现有 voice_score_from_features()，权重 10%
}

# overall 公式
# overall = content_score*0.60 + expression_score*0.30 + voice_score*0.10
```

提供函数：
- `tcl_rubric_markdown()` → 注入 stage1_prompt
- `tcl_content_score(checkpoints) -> (content_score, expression_score, dimension_scores_dict)`
- 返回三元组：DB 聚合值 × 2 + dimension_scores（用于写入 `evaluation.dimension_scores`）

### 修改 `shared/eval_core/prompt_template.py`

`stage1_prompt()` 新增可选参数 `rubric_fn=rubric_markdown`：
```python
def stage1_prompt(..., rubric_fn=rubric_markdown) -> str:
    ...
    ## 评分 rubric
    {rubric_fn()}
```

### 修改 `backend/app/services/evaluation_service.py`

按 `CompanyStyle.rubric_type` dispatch（从 Interview 关联查询获得）：
```python
rubric_type = interview.company_style.rubric_type  # "faang" | "tcl_l2"
if rubric_type == "tcl_l2":
    rubric_fn = tcl_rubric_markdown
    score_fn  = tcl_content_score   # 返回 (content, expression, dimension_scores)
else:
    rubric_fn = rubric_markdown
    score_fn  = faang_content_score  # 返回 (content, _, {})

# 写入 Evaluation 时同时写 dimension_scores
ev = Evaluation(
    ...
    dimension_scores=dimension_scores,  # 新列
)
```

---

## 双语支持

### `compose_system_prompt()` 新增 `language` 参数

- `"zh"` → 现有中文 prompt（某公司和 TCL 中文面试均走此路径）
- `"en"` → 英文 prompt template（TCL 英文面试）：
  ```
  You are a TCL interviewer conducting an L2 technical interview for the
  Embodied AI Architect role. [英文版评估要求和样题]
  ```

### `transcribe_client.submit_job()` 新增 `language_code` 参数

- `language="zh"` → `language_code="zh-CN"`
- `language="en"` → `language_code="en-US"`
- 默认 `"zh-CN"`（向后兼容）

### 语言切换行为定义

- 语言在**面试开始前**选定，面试进行中不可切换
- 语言影响：AI 提问语言、Transcribe 语言、评分 prompt 语言、报告文字语言
- 某公司固定中文，无切换选项
- TCL 默认中文，可切换为英文

---

## 前端

### `frontend/app/page.tsx` — 场景选择 UI

新增 state：
```typescript
type Scenario = { id: string; name: string; rubric_type: string }
const [scenarios, setScenarios]         = useState<Scenario[]>([])
const [selectedStyleId, setSelectedStyleId] = useState<string | null>(null)
const [selectedLang, setSelectedLang]   = useState<"zh" | "en">("zh")
```

mount 时 `GET /company-styles?builtin=true` 拉取列表；前端 metadata map 补充展示信息（由 API 下发的字段不足时使用）：
```typescript
const SCENARIO_META: Record<string, {
  roleTitle: string
  description: string
  langs: ("zh" | "en")[]
}> = {
  "某公司": {
    roleTitle: "硬件技术工程师（射频）实习生",
    description: "ICT BG 无线网络产品线 · 约 45 分钟",
    langs: ["zh"],
  },
  "TCL": {
    roleTitle: "Embodied AI Architect",
    description: "TCL EL Shanghai · L2 技术深度面 · 约 45 分钟",
    langs: ["zh", "en"],
  },
}
```

**页面首次加载**：不预选任何场景，[开始面试] 按钮 disabled，卡片区域显示提示文案"请先选择面试场景"。

卡片布局（idle 状态显示，connecting/live 状态隐藏）：
```
┌────────────────────┬──────────────────────┐
│  某公司             │  TCL                 │
│  硬件射频实习       │  Embodied AI L2      │
│  ICT BG · 约45分钟  │  Shanghai · 约45分钟 │
│  语言: 中文         │  语言: [中文] [英文]  │
│  [选中 ✓]           │                      │
└────────────────────┴──────────────────────┘
            [开始面试]
```

语言切换按钮仅在 TCL 卡片选中且 idle 状态时显示；切换语言不重置选中卡片。

`start()` 函数 WS URL 拼接：
```typescript
`${base}?token=${token}&style_id=${selectedStyleId}&lang=${selectedLang}`
```

### `frontend/app/history/[id]/page.tsx` — 评分详情页扩展

检测 `interview.company_name`，条件渲染评分块：

- `company_name !== "TCL"` → 现有三维度渲染逻辑（不变）
- `company_name === "TCL"` → 渲染 TCL 五维分块：
  ```
  技术深度    ████████░░  82 / 100
  系统架构    ███████░░░  75 / 100
  能力素质    ███████░░░  70 / 100
  文化契合    ████████░░  85 / 100
  语音表现    ██████░░░░  60 / 100
  ```
  数据来源：`evaluation.dimension_scores`（新列，由后端写入）

---

## API

### 确认/微调 `GET /company-styles`

新增 query param `?builtin=true`，返回：
```json
[
  { "id": "...", "name": "某公司", "rubric_type": "faang" },
  { "id": "...", "name": "TCL",   "rubric_type": "tcl_l2" }
]
```

---

## 改动文件汇总

| 文件 | 类型 | 说明 |
|---|---|---|
| `alembic/versions/xxxx_add_rubric_type_dimension_scores.py` | 新增 | 新增两列的 migration |
| `backend/app/models.py` | 修改 | 新增 `CompanyStyle.rubric_type`、`Evaluation.dimension_scores` |
| `backend/app/seed/tcl_style.py` | 新增 | TCL seed 数据 |
| `shared/eval_core/tcl_rubric.py` | 新增 | TCL L2 五维 rubric |
| `backend/app/main.py` | 修改 | 加 TCL seed 调用 |
| `backend/app/services/bidi_interview_session.py` | 修改 | `company_style_id` + `language` 参数，fallback 改为按 name 查 |
| `backend/app/routers/demo_bidi.py` | 修改 | 读取并校验 `style_id` + `lang` query params |
| `backend/app/services/evaluation_service.py` | 修改 | 按 `rubric_type` dispatch，写入 `dimension_scores` |
| `backend/app/clients/transcribe_client.py` | 修改 | `language_code` 参数化 |
| `shared/eval_core/prompt_template.py` | 修改 | `stage1_prompt` 加 `rubric_fn` 参数 |
| `backend/app/routers/company_styles.py` | 修改 | 确保 `?builtin=true` 可用，response 包含 `rubric_type` |
| `backend/app/schemas.py` | 修改 | `CompanyStyleResponse` 加 `rubric_type`；`EvaluationResponse` 加 `dimension_scores` |
| `frontend/app/page.tsx` | 修改 | 场景卡片 + 语言切换 + WS params |
| `frontend/app/history/[id]/page.tsx` | 修改 | TCL 五维分块条件渲染 |

**无法避免的 DB migration 一次**（新增两列，现有数据 nullable，不影响存量记录）。某公司流程逻辑路径不变。

---

## 验收标准

1. **某公司回归**：现有某公司 E2E 测试全部通过；历史详情页三维度渲染正常
2. **TCL 场景启动**：选择 TCL + 中文/英文，点击开始，WS 连接成功，AI 用对应语言开场
3. **TCL 评分**：面试结束后 `evaluation` 表有 `dimension_scores` 包含五维数据，`rubric_type` dispatch 到 `tcl_l2` 路径
4. **历史详情页 TCL**：TCL 面试详情页显示五维分块，数据与 DB 一致
5. **fallback**：`style_id` 缺失时默认加载某公司场景
6. **非法 style_id**：后端返回 WebSocket 4008，前端显示错误提示
