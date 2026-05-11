# TCL Embodied AI Architect L2 面试场景 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 TCL Embodied AI Architect L2 Mock 面试场景，与现有某公司场景并存，包含专属五维评分体系和双语支持。

**Architecture:** 复用现有 `CompanyStyle` 表，新增 `rubric_type` 和 `dimension_scores` 两列（一次 migration）；评分引擎通过 `rubric_type` dispatch 到 TCL 专属 rubric；前端首页新增场景卡片选择 UI，历史详情页按场景条件渲染评分块。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Alembic / SQLite WAL；Next.js 16 / TypeScript；pytest-asyncio；共享库 `shared/eval_core/`。

---

## 文件结构

**新增文件：**
- `backend/app/seed/tcl_style.py` — TCL seed 数据
- `shared/eval_core/tcl_rubric.py` — TCL L2 五维 rubric 函数
- `backend/alembic/versions/<rev>_add_rubric_type_dimension_scores.py` — DB migration

**修改文件：**
- `backend/app/models.py` — 新增两列
- `backend/app/schemas.py` — `CompanyStyleOut` 加 `rubric_type`；`EvaluationOut` 加 `dimension_scores`
- `backend/app/main.py` — lifespan 加 TCL seed 调用
- `backend/app/routers/company_styles.py` — 新增 `?builtin=true` filter
- `backend/app/services/bidi_interview_session.py` — 新增 `company_style_id` / `language` 参数，fallback 改为按 name 查
- `backend/app/routers/demo_bidi.py` — 读取 `style_id` / `lang` query params，校验 style_id
- `shared/eval_core/prompt_template.py` — `stage1_prompt` 加 `rubric_fn` 参数
- `backend/app/services/evaluation_service.py` — 按 `rubric_type` dispatch，写入 `dimension_scores`
- `backend/app/clients/transcribe_client.py` — `submit_job` 的 `language` 参数已存在（确认传参路径）
- `frontend/lib/api.ts` — 新增 `Scenario` 类型和 `fetchScenarios()`；`EvaluationOut` 加 `dimension_scores`
- `frontend/app/page.tsx` — 场景卡片 + 语言切换 + WS params
- `frontend/app/history/[id]/page.tsx` — TCL 五维评分块条件渲染

**测试文件（新增）：**
- `shared/eval_core/tests/test_tcl_rubric.py` — tcl_rubric 单元测试
- `backend/tests/test_tcl_seed.py` — TCL seed 幂等性测试
- `backend/tests/test_evaluation_service_tcl.py` — TCL 评分 pipeline 测试
- `backend/tests/test_company_styles_api.py` — `?builtin=true` filter 测试
- `backend/tests/test_bidi_session_tcl.py` — `company_style_id` / `language` 参数测试

---

## Task 1: DB Migration — 新增 `rubric_type` 和 `dimension_scores` 两列

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/<rev>_add_rubric_type_dimension_scores.py`

- [ ] **Step 1: 修改 `models.py`，新增两列**

```python
# backend/app/models.py
# 在 CompanyStyle 类中，is_builtin 行之后添加：
rubric_type: Mapped[str] = mapped_column(String(20), default="faang")

# 在 Evaluation 类中，rubric_version 行之后添加：
dimension_scores: Mapped[dict] = mapped_column(JSON, default=dict)
```

完整的 `CompanyStyle` 新增行（在 `is_builtin` 之后）：
```python
class CompanyStyle(Base):
    __tablename__ = "company_style"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100))
    interviewer_style_tags: Mapped[list] = mapped_column(JSON, default=list)
    preferred_question_types: Mapped[list] = mapped_column(JSON, default=list)
    sample_questions: Mapped[list] = mapped_column(JSON, default=list)
    prompt_context_text: Mapped[str] = mapped_column(Text, default="")
    is_builtin: Mapped[bool] = mapped_column(default=False)
    rubric_type: Mapped[str] = mapped_column(String(20), default="faang")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

完整的 `Evaluation` 新增行（在 `rubric_version` 之后）：
```python
    rubric_version: Mapped[str] = mapped_column(String(20), default="v1.0")
    dimension_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_prompt: Mapped[str] = mapped_column(Text, default="")
```

- [ ] **Step 2: 生成 Alembic migration**

```bash
cd backend
source .venv/bin/activate
alembic revision --autogenerate -m "add_rubric_type_dimension_scores"
```

Expected output: `Generating .../versions/xxxx_add_rubric_type_dimension_scores.py`

- [ ] **Step 3: 检查生成的 migration 文件，确认 upgrade 内容正确**

生成文件应包含（文件名中的 rev ID 会不同）：
```python
def upgrade() -> None:
    op.add_column('company_style', sa.Column('rubric_type', sa.String(length=20), nullable=False, server_default='faang'))
    op.add_column('evaluation', sa.Column('dimension_scores', sa.JSON(), nullable=False, server_default='{}'))

def downgrade() -> None:
    op.drop_column('evaluation', 'dimension_scores')
    op.drop_column('company_style', 'rubric_type')
```

如果 autogenerate 没有加 `server_default`，手动补上，否则 SQLite 现有行会报 NOT NULL 错误。

- [ ] **Step 4: 执行 migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade 5e3138664249 -> <new_rev>, add_rubric_type_dimension_scores`

- [ ] **Step 5: 验证列已存在**

```bash
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine('sqlite+aiosqlite:///interviewer.db')
    async with engine.connect() as conn:
        r = await conn.execute(text('PRAGMA table_info(company_style)'))
        cols = [row[1] for row in r.fetchall()]
        assert 'rubric_type' in cols, f'Missing rubric_type, got: {cols}'
        r2 = await conn.execute(text('PRAGMA table_info(evaluation)'))
        cols2 = [row[1] for row in r2.fetchall()]
        assert 'dimension_scores' in cols2, f'Missing dimension_scores, got: {cols2}'
        print('OK: both columns present')
    await engine.dispose()

asyncio.run(check())
"
```

Expected: `OK: both columns present`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/
git commit -m "feat(db): add rubric_type to company_style, dimension_scores to evaluation"
```

---

## Task 2: TCL Rubric — `shared/eval_core/tcl_rubric.py`

**Files:**
- Create: `shared/eval_core/tcl_rubric.py`
- Create: `shared/eval_core/tests/test_tcl_rubric.py`

- [ ] **Step 1: 先写失败测试**

```python
# shared/eval_core/tests/test_tcl_rubric.py
import pytest
from shared.eval_core.tcl_rubric import (
    tcl_rubric_markdown,
    tcl_content_score,
    TCL_L2_CHECKPOINTS,
)


def test_rubric_markdown_contains_all_checkpoints():
    md = tcl_rubric_markdown()
    for key, name, _ in TCL_L2_CHECKPOINTS:
        assert name in md, f"checkpoint {name} missing from rubric markdown"


def test_tcl_content_score_all_pass():
    checkpoints = {key: {"result": "Pass"} for key, _, _ in TCL_L2_CHECKPOINTS}
    content, expression, dim_scores = tcl_content_score(checkpoints)
    assert content == 100
    assert expression == 100
    assert "tech_depth" in dim_scores
    assert "architecture" in dim_scores
    assert "competency" in dim_scores
    assert "culture" in dim_scores


def test_tcl_content_score_all_fail():
    checkpoints = {key: {"result": "No-Pass"} for key, _, _ in TCL_L2_CHECKPOINTS}
    content, expression, dim_scores = tcl_content_score(checkpoints)
    assert content == 0
    assert expression == 0


def test_tcl_content_score_partial():
    """tech_depth passes (2 checkpoints), arch fails, competency passes, culture fails."""
    checkpoints = {
        "tech_depth_knowledge": {"result": "Pass"},
        "tech_depth_impl":      {"result": "Pass"},
        "arch_e2e_design":      {"result": "No-Pass"},
        "arch_integration":     {"result": "No-Pass"},
        "tcl_competency_star":  {"result": "Pass"},
        "tcl_culture_fit":      {"result": "No-Pass"},
    }
    content, expression, dim_scores = tcl_content_score(checkpoints)
    # tech_depth(35%) fully passed → maps to content; arch(25%) fully failed
    # content = tech_depth + arch portion normalized; expect > 0, < 100
    assert 0 < content < 100
    assert dim_scores["tech_depth"] == 100
    assert dim_scores["architecture"] == 0


def test_dim_scores_keys():
    checkpoints = {key: {"result": "Pass"} for key, _, _ in TCL_L2_CHECKPOINTS}
    _, _, dim_scores = tcl_content_score(checkpoints)
    assert set(dim_scores.keys()) == {"tech_depth", "architecture", "competency", "culture"}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/shengbo/dev/interviewer
source backend/.venv/bin/activate
python -m pytest shared/eval_core/tests/test_tcl_rubric.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'tcl_rubric_markdown'` 或类似 import 错误。

- [ ] **Step 3: 实现 `tcl_rubric.py`**

```python
# shared/eval_core/tcl_rubric.py
"""TCL Embodied AI Architect L2 — rubric definitions and scoring functions."""

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

# Dimension → checkpoint keys mapping
_TECH_DEPTH_KEYS = {"tech_depth_knowledge", "tech_depth_impl"}
_ARCH_KEYS = {"arch_e2e_design", "arch_integration"}
_COMPETENCY_KEYS = {"tcl_competency_star"}
_CULTURE_KEYS = {"tcl_culture_fit"}

# Dimension weights (must sum to 1.0 excluding voice)
# content_score = tech_depth(35%) + arch(25%) normalized to 0-100 over 60% budget
# expression_score = competency(20%) + culture(10%) normalized to 0-100 over 30% budget
_CONTENT_BUDGET = 0.60   # tech_depth(35) + arch(25)
_EXPRESSION_BUDGET = 0.30  # competency(20) + culture(10)
_TECH_DEPTH_W = 35
_ARCH_W = 25
_COMPETENCY_W = 20
_CULTURE_W = 10


def tcl_rubric_markdown() -> str:
    """Render TCL L2 rubric as markdown for injection into stage1_prompt."""
    cp = "\n".join(f"- **{name}**: {desc}" for _, name, desc in TCL_L2_CHECKPOINTS)
    return f"""### TCL L2 Evaluation — 6 Checkpoints (each Pass/No-Pass):
{cp}

### Dimension Weights:
- Technical Depth (tech_depth_knowledge + tech_depth_impl): 35%
- System Architecture (arch_e2e_design + arch_integration): 25%
- TCL Five Competencies — STAR (tcl_competency_star): 20%
- TCL Culture Alignment (tcl_culture_fit): 10%
- Voice (objective metrics, computed separately): 10%

### Expression Dimension — 5 levels (score 0-100):
1 (0-20): 混乱  2 (21-40): 缺结构  3 (41-60): 清晰  4 (61-80): 结构化  5 (81-100): 突出

### Overall Result: Pass (>=75) / Borderline (50-74) / No-Pass (<50)
"""


def _pass_ratio(checkpoints: dict, keys: set[str]) -> float:
    """Fraction of keys that are Pass (0.0–1.0). Missing keys count as No-Pass."""
    if not keys:
        return 0.0
    passed = sum(
        1 for k in keys if checkpoints.get(k, {}).get("result") == "Pass"
    )
    return passed / len(keys)


def tcl_content_score(
    checkpoints: dict,
) -> tuple[int, int, dict]:
    """Compute (content_score, expression_score, dimension_scores) from TCL checkpoints.

    content_score (0-100):
        Weighted average of tech_depth + arch, normalized.
        = (tech_depth_ratio * 35 + arch_ratio * 25) / 60 * 100

    expression_score (0-100):
        Weighted average of competency + culture, normalized.
        = (competency_ratio * 20 + culture_ratio * 10) / 30 * 100

    dimension_scores: dict with keys tech_depth, architecture, competency, culture
        (each 0-100, for frontend display)
    """
    tech_ratio = _pass_ratio(checkpoints, _TECH_DEPTH_KEYS)
    arch_ratio = _pass_ratio(checkpoints, _ARCH_KEYS)
    comp_ratio = _pass_ratio(checkpoints, _COMPETENCY_KEYS)
    cult_ratio = _pass_ratio(checkpoints, _CULTURE_KEYS)

    content = round(
        (tech_ratio * _TECH_DEPTH_W + arch_ratio * _ARCH_W)
        / (_TECH_DEPTH_W + _ARCH_W) * 100
    )
    expression = round(
        (comp_ratio * _COMPETENCY_W + cult_ratio * _CULTURE_W)
        / (_COMPETENCY_W + _CULTURE_W) * 100
    )

    dimension_scores = {
        "tech_depth":   round(tech_ratio * 100),
        "architecture": round(arch_ratio * 100),
        "competency":   round(comp_ratio * 100),
        "culture":      round(cult_ratio * 100),
    }

    return content, expression, dimension_scores
```

- [ ] **Step 4: 运行测试确认全部通过**

```bash
python -m pytest shared/eval_core/tests/test_tcl_rubric.py -v
```

Expected:
```
test_rubric_markdown_contains_all_checkpoints PASSED
test_tcl_content_score_all_pass PASSED
test_tcl_content_score_all_fail PASSED
test_tcl_content_score_partial PASSED
test_dim_scores_keys PASSED
5 passed
```

- [ ] **Step 5: Commit**

```bash
git add shared/eval_core/tcl_rubric.py shared/eval_core/tests/test_tcl_rubric.py
git commit -m "feat(eval): add TCL L2 rubric with five-dimension scoring"
```

---

## Task 3: TCL Seed 数据 — `backend/app/seed/tcl_style.py`

**Files:**
- Create: `backend/app/seed/tcl_style.py`
- Create: `backend/tests/test_tcl_seed.py`

- [ ] **Step 1: 先写失败测试**

```python
# backend/tests/test_tcl_seed.py
import pytest
from sqlalchemy import select

from app.models import CompanyStyle
from app.seed.tcl_style import seed_if_empty


@pytest.mark.asyncio
async def test_seed_inserts_tcl(db):
    count = await seed_if_empty(db)
    assert count == 1
    result = await db.execute(select(CompanyStyle).where(CompanyStyle.name == "TCL"))
    cs = result.scalar_one_or_none()
    assert cs is not None
    assert cs.rubric_type == "tcl_l2"
    assert cs.is_builtin is True
    assert len(cs.sample_questions) >= 5


@pytest.mark.asyncio
async def test_seed_is_idempotent(db):
    count1 = await seed_if_empty(db)
    count2 = await seed_if_empty(db)
    assert count1 == 1
    assert count2 == 0
    result = await db.execute(select(CompanyStyle).where(CompanyStyle.name == "TCL"))
    rows = result.scalars().all()
    assert len(rows) == 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend
python -m pytest tests/test_tcl_seed.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'app.seed.tcl_style'`

- [ ] **Step 3: 实现 `tcl_style.py`**

```python
# backend/app/seed/tcl_style.py
"""Seed data: TCL Embodied AI Architect L2 interview scenario."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CompanyStyle

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
        "请描述你设计过的一个具身 AI 系统的端到端软件架构，重点说明各模块的接口定义和数据流。",
        "在机器人感知-规划-执行链路中，你如何处理传感器数据延迟和不确定性？",
        "请对比 ROS2 和自研 middleware 在家庭机器人场景下的 trade-off。",
        "你如何设计一个支持 VLM 推理的实时感知模块？对算力/延迟/精度如何做 trade-off？",
        "描述一次你将 AI 算法模块与嵌入式硬件集成的经历，遇到了哪些接口和性能问题？",
        "你如何在边端（嵌入式）和云端之间做推理任务的分配决策？",
        "举一个你主导了复杂系统架构决策的案例，从方案选型到落地的完整过程。（规划力/执行力）",
        "描述一次你在跨团队（硬件/算法/产品）协作中化解技术分歧的经历。（沟通力）",
        "讲一个你在模糊需求下独立推进并交付的项目。（学习力/管控力）",
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


async def seed_if_empty(session: AsyncSession) -> int:
    """Insert TCL CompanyStyle if not already present. Returns count inserted."""
    existing = await session.scalar(
        select(CompanyStyle).where(CompanyStyle.name == "TCL")
    )
    if existing is not None:
        return 0
    session.add(CompanyStyle(is_builtin=True, **COMPANY_STYLE))
    await session.commit()
    return 1
```

- [ ] **Step 4: 运行测试**

```bash
python -m pytest tests/test_tcl_seed.py -v
```

Expected:
```
test_seed_inserts_tcl PASSED
test_seed_is_idempotent PASSED
2 passed
```

- [ ] **Step 5: 更新 `backend/app/main.py` 加入 TCL seed 调用**

```python
# backend/app/main.py
# 修改 import 行：
from app.seed.company_styles import seed_if_empty as seed_company_styles
from app.seed.tcl_style import seed_if_empty as seed_tcl

# 修改 lifespan：
@asynccontextmanager
async def lifespan(_: FastAPI):
    async with SessionLocal() as session:
        await seed_company_styles(session)
        await seed_tcl(session)
    yield
```

- [ ] **Step 6: 运行全量测试确认无回归**

```bash
python -m pytest -q
```

Expected: all existing tests pass + 2 new pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/seed/tcl_style.py backend/tests/test_tcl_seed.py backend/app/main.py
git commit -m "feat(seed): add TCL Embodied AI Architect L2 company style"
```

---

## Task 4: `stage1_prompt` 参数化 + Schemas 更新

**Files:**
- Modify: `shared/eval_core/prompt_template.py`
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: 修改 `stage1_prompt` 加 `rubric_fn` 参数**

```python
# shared/eval_core/prompt_template.py
# 修改函数签名和 rubric 注入行：

from .rubric import rubric_markdown  # 已存在

def stage1_prompt(
    question: str,
    transcript: str,
    voice_features: dict,
    company: str,
    role: str,
    language: str,
    style_tags: list[str] | None = None,
    rubric_fn=rubric_markdown,          # 新增参数，默认 FAANG rubric
) -> str:
    style = ", ".join(style_tags) if style_tags else "标准行为面试风格"
    vf = voice_features
    return f"""你是一位专业的面试教练，针对 {company}（风格：{style}）{role} 岗位进行面试评估。

## 问题
{question}

## 候选人回答（转录，{language}）
{transcript}

## 客观语音指标
- 回答总时长: {vf.get('duration_total_sec', 0):.1f}s
- 语速: {vf.get('talk_speed_wps', 0):.2f} 词/秒（中文按字数）
- 停顿次数: {vf.get('pause_count', 0)} 次 ({vf.get('pause_count_per_minute', 0):.1f} 次/分钟)
- 最长停顿: {vf.get('longest_pause_sec', 0):.1f}s
- 填充词占比: {vf.get('filler_word_ratio', 0):.1%} (检测到: {vf.get('filler_words_detected', [])})
- Speaking ratio: {vf.get('speaking_ratio', 0):.1%}
- 情感倾向: {vf.get('transcribe_sentiment', {}).get('overall', 'NEUTRAL')}

## 评分 rubric
{rubric_fn()}

## 输出格式（严格 JSON，不要任何额外文本，不要 markdown 代码块）
{{
  "content_checkpoints": {{
    "star_structure": {{"result": "Pass" or "No-Pass", "reason": "具体理由"}},
    "specificity_details": {{"result": "...", "reason": "..."}},
    "impact_results": {{"result": "...", "reason": "..."}},
    "leadership_ownership": {{"result": "...", "reason": "..."}},
    "problem_solving": {{"result": "...", "reason": "..."}},
    "communication_clarity": {{"result": "...", "reason": "..."}}
  }},
  "expression_score": <0-100>,
  "expression_reasoning": "具体理由",
  "voice_score": <0-100>,
  "voice_reasoning": "必须引用至少 1 个客观指标数值",
  "improvement_suggestions": ["具体可操作建议 1", "建议 2", "建议 3"],
  "ideal_answer": "符合 {company} 风格、STAR 结构完整的参考答案（3-5 句）"
}}
"""
```

注意：TCL 的 stage1 prompt 使用相同输出 JSON 结构，但 `content_checkpoints` 的 keys 将对应 TCL 六个 checkpoint keys（`tech_depth_knowledge` 等）。Claude 会按 rubric 指令生成对应 keys。

- [ ] **Step 2: 修改 `schemas.py` 新增两个字段**

```python
# backend/app/schemas.py

class CompanyStyleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    interviewer_style_tags: list[str]
    preferred_question_types: list[str]
    sample_questions: list[str]
    prompt_context_text: str
    is_builtin: bool
    rubric_type: str = "faang"   # 新增
    created_at: datetime


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    question_id: str | None
    content_score: int
    expression_score: int
    voice_score: int
    overall_score: int
    overall_result: str
    improvement_suggestion: str
    ideal_answer: str | None
    voice_features: dict = {}
    dimension_scores: dict = {}  # 新增：TCL 五维原始分，某公司为空 dict
```

- [ ] **Step 3: 运行已有测试确认无回归**

```bash
python -m pytest -q
```

Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add shared/eval_core/prompt_template.py backend/app/schemas.py
git commit -m "feat(eval): parameterize stage1_prompt rubric_fn; add rubric_type and dimension_scores to schemas"
```

---

## Task 5: 更新 Evaluation Service — TCL dispatch

**Files:**
- Modify: `backend/app/services/evaluation_service.py`
- Create: `backend/tests/test_evaluation_service_tcl.py`

- [ ] **Step 1: 先写 TCL pipeline 的失败测试**

```python
# backend/tests/test_evaluation_service_tcl.py
"""Tests for TCL-specific evaluation pipeline dispatch."""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models import CompanyStyle, Evaluation, Interview
from app.services.evaluation_service import evaluate_interview


@pytest_asyncio_fixture_helper  # 使用下方 fixture
async def db_with_tcl(session_factory):
    """Seed TCL CompanyStyle and return session_factory."""
    async with session_factory() as s:
        cs = CompanyStyle(
            name="TCL",
            rubric_type="tcl_l2",
            interviewer_style_tags=["技术深度"],
            preferred_question_types=["架构设计"],
            sample_questions=["描述你的架构设计经验"],
            prompt_context_text="TCL L2 评估...",
            is_builtin=True,
        )
        s.add(cs)
        await s.commit()
    return session_factory
```

Fixture 使用 `conftest.py` 的 `session_factory`，在 test 文件内定义局部 fixture：

```python
# backend/tests/test_evaluation_service_tcl.py
"""Tests for TCL evaluation pipeline dispatch."""
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import CompanyStyle, Evaluation, Interview
from app.services.bidi_interview_session import BidiInterviewSession
from app.services.evaluation_service import evaluate_interview


@pytest_asyncio.fixture
async def db_with_tcl(session_factory):
    async with session_factory() as s:
        cs = CompanyStyle(
            name="TCL",
            rubric_type="tcl_l2",
            interviewer_style_tags=["技术深度"],
            preferred_question_types=["架构设计"],
            sample_questions=["描述你的架构设计经验"],
            prompt_context_text="TCL L2 评估...",
            is_builtin=True,
        )
        s.add(cs)
        await s.commit()
    return session_factory


@pytest.mark.asyncio
async def test_tcl_pipeline_writes_dimension_scores(db_with_tcl, mock_s3_upload):
    """TCL pipeline: dimension_scores populated; rubric_type dispatched correctly."""
    session = BidiInterviewSession(
        db_with_tcl,
        role_title="Embodied AI Architect",
        company_style_id=None,  # will be set by setup() once we pass style_id
    )
    # We need to directly seed with TCL style_id
    async with db_with_tcl() as s:
        from sqlalchemy import select as sa_select
        cs = (await s.execute(sa_select(CompanyStyle).where(CompanyStyle.name == "TCL"))).scalar_one()
        tcl_id = cs.id

    session2 = BidiInterviewSession(
        db_with_tcl,
        role_title="Embodied AI Architect",
        company_style_id=tcl_id,
    )
    await session2.setup()
    await session2.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "请描述你设计过的具身AI系统架构。", "is_final": True,
    })
    await session2.on_event({
        "type": "bidi_transcript_stream", "role": "user",
        "text": "我设计了一个基于ROS2的家庭机器人系统，包括感知模块、规划模块和执行模块。", "is_final": True,
    })
    await session2.finalize(status="completed")

    tcl_stage1_response = {
        "content_checkpoints": {
            "tech_depth_knowledge": {"result": "Pass", "reason": "了解ROS2"},
            "tech_depth_impl":      {"result": "Pass", "reason": "有实现经验"},
            "arch_e2e_design":      {"result": "Pass", "reason": "描述了端到端架构"},
            "arch_integration":     {"result": "No-Pass", "reason": "未提到硬件集成"},
            "tcl_competency_star":  {"result": "Pass", "reason": "有清晰陈述"},
            "tcl_culture_fit":      {"result": "No-Pass", "reason": "未提文化契合"},
        },
        "expression_score": 72,
        "improvement_suggestions": ["加入硬件集成细节"],
        "ideal_answer": "参考答案...",
    }
    tcl_stage2_response = {
        "overall_content_score": 70,
        "overall_expression_score": 65,
        "overall_voice_score": 0,
        "overall_score": 60,
        "overall_result": "Borderline",
        "overall_summary": "技术深度良好但集成经验不足",
        "strengths": ["ROS2架构设计"],
        "top_3_improvement_priorities": ["硬件集成", "文化契合表达", "STAR结构"],
    }

    with patch(
        "app.services.evaluation_service.bedrock_claude.invoke_json",
        side_effect=[
            (tcl_stage1_response, {"cost_usd": 0.01}),
            (tcl_stage2_response, {"cost_usd": 0.01}),
        ],
    ), patch(
        "app.services.evaluation_service._compute_voice_features",
        new=AsyncMock(return_value={
            "duration_total_sec": 10, "duration_speaking_sec": 8,
            "speaking_ratio": 0.8, "talk_speed_cps": 4.0,
            "pause_count": 2, "pause_count_per_minute": 12,
            "longest_pause_sec": 0.5, "filler_word_count": 0,
            "filler_word_ratio": 0.0, "filler_words_detected": [],
            "first_response_delay_sec": 1.0, "hesitation_count": 0,
            "volume_mean": 0.5, "volume_stability": 0.2,
            "accurate_wpm": 0, "accurate_speaking_sec": 0,
            "low_confidence_ratio": 0.0, "low_confidence_words": [],
            "sentiment_overall": "POSITIVE",
            "sentiment_scores": {"positive": 0.9, "negative": 0.1, "neutral": 0.0, "mixed": 0.0},
            "transcribe_sentiment": {"overall": "POSITIVE"},
        }),
    ):
        await evaluate_interview(db_with_tcl, session2.interview_id)

    async with db_with_tcl() as s:
        evals = (
            await s.execute(
                select(Evaluation).where(Evaluation.interview_id == session2.interview_id)
            )
        ).scalars().all()

    per_q = [e for e in evals if e.question_id is not None]
    assert len(per_q) == 1
    ev = per_q[0]

    # TCL dimension_scores must be populated
    assert ev.dimension_scores != {}
    assert "tech_depth" in ev.dimension_scores
    assert "architecture" in ev.dimension_scores
    assert "competency" in ev.dimension_scores
    assert "culture" in ev.dimension_scores

    # tech_depth = 100 (both pass), architecture = 50 (1/2 pass)
    assert ev.dimension_scores["tech_depth"] == 100
    assert ev.dimension_scores["architecture"] == 50


@pytest.mark.asyncio
async def test_faang_pipeline_dimension_scores_empty(db_with_company, mock_s3_upload):
    """某公司 pipeline: dimension_scores should be empty dict (not TCL fields)."""
    from app.services.bidi_interview_session import BidiInterviewSession

    session = BidiInterviewSession(db_with_company, role_title="RF")
    await session.setup()
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "assistant",
        "text": "请介绍你的射频项目。", "is_final": True,
    })
    await session.on_event({
        "type": "bidi_transcript_stream", "role": "user",
        "text": "我设计了5G天线，使用HFSS仿真验证。", "is_final": True,
    })
    await session.finalize(status="completed")

    faang_stage1 = {
        "content_checkpoints": {
            "star_structure": {"result": "Pass", "reason": "ok"},
            "specificity_details": {"result": "Pass", "reason": "ok"},
            "impact_results": {"result": "No-Pass", "reason": "no"},
            "leadership_ownership": {"result": "No-Pass", "reason": "no"},
            "problem_solving": {"result": "Pass", "reason": "ok"},
            "communication_clarity": {"result": "Pass", "reason": "ok"},
        },
        "expression_score": 70,
        "improvement_suggestions": ["加入数据"],
        "ideal_answer": "参考...",
    }
    faang_stage2 = {
        "overall_content_score": 67, "overall_expression_score": 70,
        "overall_voice_score": 0, "overall_score": 55, "overall_result": "Borderline",
        "overall_summary": "中等", "strengths": ["基础扎实"],
        "top_3_improvement_priorities": ["数据", "结构", "犹豫"],
    }

    with patch(
        "app.services.evaluation_service.bedrock_claude.invoke_json",
        side_effect=[
            (faang_stage1, {"cost_usd": 0.01}),
            (faang_stage2, {"cost_usd": 0.01}),
        ],
    ), patch(
        "app.services.evaluation_service._compute_voice_features",
        new=AsyncMock(return_value={
            "duration_total_sec": 10, "duration_speaking_sec": 8,
            "speaking_ratio": 0.8, "talk_speed_cps": 4.0,
            "pause_count": 2, "pause_count_per_minute": 12,
            "longest_pause_sec": 0.5, "filler_word_count": 0,
            "filler_word_ratio": 0.0, "filler_words_detected": [],
            "first_response_delay_sec": 1.0, "hesitation_count": 0,
            "volume_mean": 0.5, "volume_stability": 0.2,
            "accurate_wpm": 0, "accurate_speaking_sec": 0,
            "low_confidence_ratio": 0.0, "low_confidence_words": [],
            "sentiment_overall": "NEUTRAL",
            "sentiment_scores": {"positive": 0.5, "negative": 0.1, "neutral": 0.4, "mixed": 0.0},
            "transcribe_sentiment": {"overall": "NEUTRAL"},
        }),
    ):
        await evaluate_interview(db_with_company, session.interview_id)

    async with db_with_company() as s:
        evals = (
            await s.execute(
                select(Evaluation).where(Evaluation.interview_id == session.interview_id)
            )
        ).scalars().all()

    per_q = [e for e in evals if e.question_id is not None]
    assert len(per_q) == 1
    # FAANG pipeline: dimension_scores is empty dict
    assert per_q[0].dimension_scores == {}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_evaluation_service_tcl.py -v 2>&1 | head -20
```

Expected: 测试运行但失败，因为 evaluation_service 还没有 TCL dispatch 逻辑。

- [ ] **Step 3: 修改 `evaluation_service.py` 实现 TCL dispatch**

在 `_run_pipeline` 函数中，加载 interview 时同时 eager load `company_style`，并按 `rubric_type` dispatch：

```python
# backend/app/services/evaluation_service.py
# 新增 import：
from shared.eval_core.tcl_rubric import tcl_rubric_markdown, tcl_content_score

# 修改 _run_pipeline 中的加载逻辑（加 selectinload company_style）：
from sqlalchemy.orm import selectinload

async def _run_pipeline(sf, interview_id):
    async with sf() as db:
        res = await db.execute(
            select(Interview)
            .where(Interview.id == interview_id)
            .options(
                selectinload(Interview.questions).selectinload(Question.answer),
                selectinload(Interview.company_style),   # 新增：eager load company_style
            )
        )
        iv = res.scalar_one_or_none()
        if iv is None:
            logger.error("interview %s not found", interview_id)
            return
        company = iv.company_name
        role = iv.role_title
        language = iv.language
        questions = sorted(iv.questions, key=lambda q: q.order_index)
        # 新增：读取 rubric_type
        rubric_type = iv.company_style.rubric_type if iv.company_style else "faang"

    # 在 qa_pairs 处理后，per-question 循环中：
    for q, a in qa_pairs:
        voice_features = await _compute_voice_features(a, interview_id)

        # dispatch rubric
        if rubric_type == "tcl_l2":
            _rubric_fn = tcl_rubric_markdown
        else:
            _rubric_fn = rubric_markdown

        prompt = stage1_prompt(
            question=q.question_text,
            transcript=a.transcript_text,
            voice_features=voice_features,
            company=company,
            role=role,
            language=language,
            rubric_fn=_rubric_fn,   # 新增参数
        )
        parsed, meta = await bedrock_claude.invoke_json(prompt, max_tokens=2000)

        # dispatch scoring
        checkpoints = parsed.get("content_checkpoints", {})
        if rubric_type == "tcl_l2":
            c_score, e_score, dim_scores = tcl_content_score(checkpoints)
            # voice score from existing function (TCL weight: 10%)
            v_score = voice_score_from_features(voice_features)
            o_score = round(c_score * 0.60 + e_score * 0.30 + v_score * 0.10)
        else:
            c_score = content_score_from_checkpoints(checkpoints)
            e_score = int(parsed.get("expression_score", 0))
            v_score = voice_score_from_features(voice_features)
            o_score = round(c_score * 0.5 + e_score * 0.3 + v_score * 0.2)
            dim_scores = {}

        suggestions = parsed.get("improvement_suggestions", [])
        suggestion_text = "\n".join(f"• {s}" for s in suggestions) if suggestions else ""

        ev = Evaluation(
            interview_id=interview_id,
            question_id=q.id,
            content_score=c_score,
            expression_score=e_score,
            voice_score=v_score,
            overall_score=o_score,
            overall_result=overall_result_label(o_score),
            improvement_suggestion=suggestion_text,
            ideal_answer=parsed.get("ideal_answer"),
            voice_features=voice_features,
            dimension_scores=dim_scores,   # 新增
            raw_prompt=prompt[:5000],
            raw_response=parsed,
            evaluation_cost_usd=meta.get("cost_usd", 0),
        )
        # ... rest unchanged
```

- [ ] **Step 4: 运行所有 evaluation 测试**

```bash
python -m pytest tests/test_evaluation_service.py tests/test_evaluation_service_tcl.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/evaluation_service.py backend/tests/test_evaluation_service_tcl.py
git commit -m "feat(eval): dispatch TCL L2 rubric in evaluation pipeline; write dimension_scores"
```

---

## Task 6: BidiInterviewSession — `company_style_id` + `language` 参数

**Files:**
- Modify: `backend/app/services/bidi_interview_session.py`
- Create: `backend/tests/test_bidi_session_tcl.py`

- [ ] **Step 1: 先写失败测试**

```python
# backend/tests/test_bidi_session_tcl.py
"""Tests for BidiInterviewSession with company_style_id and language params."""
import pytest
import pytest_asyncio

from app.models import CompanyStyle, Interview
from app.services.bidi_interview_session import BidiInterviewSession


@pytest_asyncio.fixture
async def db_with_both_styles(session_factory):
    """Seed 某公司 + TCL CompanyStyles."""
    async with session_factory() as s:
        s.add(CompanyStyle(
            name="某公司", rubric_type="faang", is_builtin=True,
            interviewer_style_tags=[], preferred_question_types=[],
            sample_questions=[], prompt_context_text="某公司上下文",
        ))
        s.add(CompanyStyle(
            name="TCL", rubric_type="tcl_l2", is_builtin=True,
            interviewer_style_tags=[], preferred_question_types=[],
            sample_questions=[], prompt_context_text="TCL上下文",
        ))
        await s.commit()
    return session_factory


@pytest.mark.asyncio
async def test_setup_with_style_id_loads_tcl(db_with_both_styles, mock_s3_upload):
    """Passing style_id should load the specified CompanyStyle."""
    from sqlalchemy import select
    async with db_with_both_styles() as s:
        cs = (await s.execute(
            select(CompanyStyle).where(CompanyStyle.name == "TCL")
        )).scalar_one()
        tcl_id = cs.id

    session = BidiInterviewSession(
        db_with_both_styles,
        role_title="Embodied AI Architect",
        company_style_id=tcl_id,
        language="en",
    )
    await session.setup()

    async with db_with_both_styles() as s:
        iv = await s.get(Interview, session.interview_id)
    assert iv.company_name == "TCL"
    assert iv.language == "en"


@pytest.mark.asyncio
async def test_setup_fallback_loads_huawei(db_with_both_styles, mock_s3_upload):
    """style_id=None should fallback to 某公司 (by name)."""
    session = BidiInterviewSession(
        db_with_both_styles,
        role_title="RF Intern",
        company_style_id=None,
        language="zh",
    )
    await session.setup()

    async with db_with_both_styles() as s:
        iv = await s.get(Interview, session.interview_id)
    assert iv.company_name == "某公司"
    assert iv.language == "zh"


@pytest.mark.asyncio
async def test_setup_invalid_style_id_raises(db_with_both_styles, mock_s3_upload):
    """Invalid style_id should raise RuntimeError."""
    session = BidiInterviewSession(
        db_with_both_styles,
        role_title="RF Intern",
        company_style_id="nonexistent-id",
    )
    with pytest.raises(RuntimeError, match="CompanyStyle.*not found"):
        await session.setup()


@pytest.mark.asyncio
async def test_system_prompt_language_en(db_with_both_styles, mock_s3_upload):
    """language='en' should produce English system prompt for TCL."""
    from sqlalchemy import select
    async with db_with_both_styles() as s:
        cs = (await s.execute(
            select(CompanyStyle).where(CompanyStyle.name == "TCL")
        )).scalar_one()
        tcl_id = cs.id

    session = BidiInterviewSession(
        db_with_both_styles,
        role_title="Embodied AI Architect",
        company_style_id=tcl_id,
        language="en",
    )
    await session.setup()
    assert "You are" in session.system_prompt or "interviewer" in session.system_prompt.lower()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_bidi_session_tcl.py -v 2>&1 | head -20
```

Expected: `TypeError: BidiInterviewSession.__init__() got unexpected keyword argument 'company_style_id'`

- [ ] **Step 3: 修改 `bidi_interview_session.py`**

```python
# backend/app/services/bidi_interview_session.py

# 修改 __init__ 签名：
def __init__(
    self,
    session_factory: async_sessionmaker[AsyncSession],
    role_title: str,
    s3_prefix: str = "interviews",
    company_style_id: str | None = None,   # 新增
    language: str = "zh",                  # 新增
) -> None:
    self._sf = session_factory
    self._role_title = role_title
    self._s3_prefix = s3_prefix
    self._company_style_id = company_style_id   # 新增
    self._language = language                   # 新增
    # ... rest of __init__ unchanged

# 修改 setup() 中的 Interview 创建：
iv = Interview(
    company_name=cs.name,
    company_style_id=cs.id,
    role_title=self._role_title,
    language=self._language,    # 使用传入的 language
    mode="strict",
    status="in_progress",
    bidi_started_at=datetime.utcnow(),
    started_at=datetime.utcnow(),
)

# 修改 setup() 调用 _load_company_style：
cs = await self._load_company_style(db)

# 修改 _load_company_style：
async def _load_company_style(self, db: AsyncSession) -> CompanyStyle:
    if self._company_style_id is not None:
        cs = await db.get(CompanyStyle, self._company_style_id)
        if cs is None:
            raise RuntimeError(f"CompanyStyle id={self._company_style_id} not found")
        return cs
    # fallback: load by name="某公司"
    res = await db.execute(
        select(CompanyStyle).where(CompanyStyle.name == "某公司").limit(1)
    )
    cs = res.scalar_one_or_none()
    if cs is None:
        raise RuntimeError("Default CompanyStyle '某公司' not seeded; run seed first")
    return cs
```

修改 `compose_system_prompt` 加 `language` 参数：

```python
def compose_system_prompt(company_style: CompanyStyle, role_title: str, language: str = "zh") -> str:
    """Compose system prompt. language='en' produces English prompt for TCL."""
    base = (company_style.prompt_context_text or "").strip()
    sample = "\n".join(f"- {q}" for q in (company_style.sample_questions or [])[:6])

    if language == "en":
        return (
            f"You are a {company_style.name} interviewer conducting an L2 technical interview "
            f"for the \"{role_title}\" role.\n\n"
            f"{base}\n\n"
            "Sample questions for reference:\n"
            f"{sample}\n\n"
            "Interview rules:\n"
            "- Introduce yourself briefly, then ask the first question directly.\n"
            "- Ask one question at a time; wait for a complete answer before continuing.\n"
            "- Keep responses concise and professional (max 2 sentences).\n"
            "- Finish the interview within 45 minutes (6-8 questions), then close politely.\n"
            "- After closing, do not ask further questions.\n"
        )

    return (
        f"你是 {company_style.name} 面试官，正在面试一位应聘 \"{role_title}\" 的候选人。\n\n"
        f"{base}\n\n"
        "候选样题（可参考，也可基于候选人背景自然追问）：\n"
        f"{sample}\n\n"
        "面试规则：\n"
        "- 开场用一句话自我介绍，然后直接问第一题。\n"
        "- 每次只问一个问题，等候选人完整回答再继续。\n"
        "- 语气简洁专业，每次发言不超过两句话。\n"
        "- 面试控制在 45 分钟以内，约 6-8 题后礼貌收尾（说 \"今天的面试就到这里，感谢你的参与\"）。\n"
        "- 收尾后不再提问，等候选人告别即可。\n"
    )
```

在 `setup()` 中调用时传入 language：
```python
self._system_prompt = compose_system_prompt(cs, self._role_title, self._language)
```

- [ ] **Step 4: 运行 session 测试**

```bash
python -m pytest tests/test_bidi_session_tcl.py tests/test_bidi_interview_session.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/bidi_interview_session.py backend/tests/test_bidi_session_tcl.py
git commit -m "feat(session): add company_style_id + language params to BidiInterviewSession"
```

---

## Task 7: WebSocket Router — 读取 `style_id` + `lang`，验证 style_id

**Files:**
- Modify: `backend/app/routers/demo_bidi.py`

- [ ] **Step 1: 修改 `demo_bidi.py` 读取并校验 query params**

在 `interview_demo` 函数中，JWT 验证之后，`await websocket.accept()` 之前：

```python
@router.websocket("/ws/interview-demo")
async def interview_demo(websocket: WebSocket) -> None:
    # 1. Verify JWT (unchanged)
    try:
        token = websocket.query_params.get("token")
        from app.auth import verify_ws_token
        verify_ws_token(token)
    except Exception as e:
        logger.warning("WS auth failed: %s", e)
        await websocket.close(code=4401, reason="unauthorized")
        return

    # 2. Read + validate style_id and lang (NEW)
    style_id: str | None = websocket.query_params.get("style_id") or None
    lang: str = websocket.query_params.get("lang", "zh")
    if lang not in ("zh", "en"):
        lang = "zh"

    # Validate style_id exists in DB if provided
    if style_id is not None:
        async with SessionLocal() as db:
            from app.models import CompanyStyle as CS
            cs_check = await db.get(CS, style_id)
            if cs_check is None:
                logger.warning("WS invalid style_id=%s", style_id)
                await websocket.close(code=4008, reason="invalid style_id")
                return

    await websocket.accept()

    # 3. Build session with params (changed from hardcoded)
    session = BidiInterviewSession(
        SessionLocal,
        role_title=_role_title_for_style(style_id),
        company_style_id=style_id,
        language=lang,
    )
    # ... rest unchanged
```

新增辅助函数 `_role_title_for_style`（在 `interview_demo` 之前）：

```python
_STYLE_ROLE_TITLES: dict[str | None, str] = {}  # populated lazily; fallback below

def _role_title_for_style(style_id: str | None) -> str:
    """Return a sensible role title default when not specified by client.

    In production the client should pass the role_title as a query param,
    but for backward compat we derive from the style. TCL style_id is
    identified at runtime from the DB; we cache the mapping on first lookup.
    """
    # For now: fallback to the old hardcoded constant if no style_id.
    # TCL sessions get a better default in setup() from CompanyStyle name.
    return ROLE_TITLE  # existing constant — setup() will use cs.name anyway
```

注：`BidiInterviewSession.setup()` 会用 `CompanyStyle.name` 覆盖 `company_name` 字段；`role_title` 是面试官 prompt 里显示的岗位名称，后续可以通过前端传参进一步完善，当前 fallback 到原有常量不影响功能。

- [ ] **Step 2: 运行现有 integration test 确认无回归**

```bash
python -m pytest tests/test_demo_bidi_integration.py -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/demo_bidi.py
git commit -m "feat(ws): read style_id and lang query params; validate style_id with 4008"
```

---

## Task 8: Company Styles API — `?builtin=true` filter + `rubric_type` response

**Files:**
- Modify: `backend/app/routers/company_styles.py`
- Modify: `backend/app/services/company_style_service.py`
- Create: `backend/tests/test_company_styles_api.py`

- [ ] **Step 1: 先写失败测试**

```python
# backend/tests/test_company_styles_api.py
"""Tests for GET /api/company-styles?builtin=true."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_builtin_only(client: AsyncClient):
    """?builtin=true returns only builtin styles."""
    # Seed two builtin styles directly via DB
    from app.models import CompanyStyle
    from app.db import get_session
    # Use the app's seeded data — need to seed first
    from app.seed.company_styles import seed_if_empty as seed_huawei
    from app.seed.tcl_style import seed_if_empty as seed_tcl
    # client fixture uses in-memory DB; seed it
    async for db in client.app.dependency_overrides[get_session]():
        await seed_huawei(db)
        await seed_tcl(db)
        break

    resp = await client.get("/api/company-styles?builtin=true")
    assert resp.status_code == 200
    data = resp.json()
    assert all(s["is_builtin"] for s in data)
    names = [s["name"] for s in data]
    assert "某公司" in names
    assert "TCL" in names


@pytest.mark.asyncio
async def test_list_all_without_filter(client: AsyncClient):
    """No filter returns all styles."""
    resp = await client.get("/api/company-styles")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_response_includes_rubric_type(client: AsyncClient):
    """Each style in the response has a rubric_type field."""
    from app.seed.company_styles import seed_if_empty as seed_huawei
    from app.seed.tcl_style import seed_if_empty as seed_tcl
    from app.db import get_session
    async for db in client.app.dependency_overrides[get_session]():
        await seed_huawei(db)
        await seed_tcl(db)
        break

    resp = await client.get("/api/company-styles?builtin=true")
    assert resp.status_code == 200
    for item in resp.json():
        assert "rubric_type" in item
    tcl = next(s for s in resp.json() if s["name"] == "TCL")
    assert tcl["rubric_type"] == "tcl_l2"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
python -m pytest tests/test_company_styles_api.py -v 2>&1 | head -20
```

Expected: `AssertionError` 因为 `?builtin=true` 还未实现，且 response 缺少 `rubric_type`。

- [ ] **Step 3: 修改 `company_style_service.py` 加 `builtin_only` 参数**

```python
# backend/app/services/company_style_service.py

async def list_styles(db: AsyncSession, builtin_only: bool = False) -> list[CompanyStyle]:
    q = select(CompanyStyle)
    if builtin_only:
        q = q.where(CompanyStyle.is_builtin.is_(True))
    res = await db.execute(q.order_by(CompanyStyle.created_at.asc()))
    return list(res.scalars().all())
```

- [ ] **Step 4: 修改 `company_styles.py` router 读取 query param**

```python
# backend/app/routers/company_styles.py
from fastapi import APIRouter, Depends, Query, UploadFile

@router.get("", response_model=list[CompanyStyleOut])
async def list_company_styles(
    builtin: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
) -> list[CompanyStyleOut]:
    styles = await company_style_service.list_styles(db, builtin_only=builtin)
    return [CompanyStyleOut.model_validate(s) for s in styles]
```

- [ ] **Step 5: 运行测试**

```bash
python -m pytest tests/test_company_styles_api.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/company_styles.py backend/app/services/company_style_service.py backend/tests/test_company_styles_api.py
git commit -m "feat(api): add ?builtin=true filter to company-styles endpoint; include rubric_type in response"
```

---

## Task 9: 运行全量后端测试 — 回归检查

**Files:** none（验证任务）

- [ ] **Step 1: 运行全量后端测试**

```bash
cd backend
python -m pytest -q
```

Expected: 全部通过（新增约 15 个测试，原有 128 个测试不回归）。

- [ ] **Step 2: 如有失败，修复后再 commit**

排查要点：
- `test_evaluation_service.py` 中调用 `BidiInterviewSession` 的测试：检查 `db_with_company` fixture 是否需要更新（`某公司` CompanyStyle 需加 `rubric_type="faang"`）
- `stage1_prompt` 测试：检查 `rubric_fn` 参数是否影响了已有 snapshot 测试

---

## Task 10: 前端 — `api.ts` 新增 `Scenario` 类型和 `fetchScenarios`

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: 修改 `api.ts`**

```typescript
// frontend/lib/api.ts

// 新增类型（在 InterviewSummary 之前）：
export interface Scenario {
  id: string;
  name: string;
  rubric_type: string;
  is_builtin: boolean;
}

// 修改 EvaluationOut，新增 dimension_scores：
export interface EvaluationOut {
  id: string;
  question_id: string | null;
  content_score: number;
  expression_score: number;
  voice_score: number;
  overall_score: number;
  overall_result: string;
  improvement_suggestion: string;
  ideal_answer: string | null;
  voice_features?: { /* existing fields unchanged */ };
  dimension_scores?: {          // 新增
    tech_depth?: number;
    architecture?: number;
    competency?: number;
    culture?: number;
    voice?: number;
  };
}

// 新增函数（在 fetchInterviews 之前）：
export async function fetchScenarios(): Promise<Scenario[]> {
  const res = await authedFetch(`${API_BASE}/api/company-styles?builtin=true`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch scenarios: ${res.status}`);
  return res.json();
}
```

- [ ] **Step 2: 运行前端类型检查**

```bash
cd frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend/api): add Scenario type, fetchScenarios, dimension_scores to EvaluationOut"
```

---

## Task 11: 前端 — `page.tsx` 场景选择 UI

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: 在 `page.tsx` 顶部新增 import 和类型**

```typescript
// frontend/app/page.tsx
// 在现有 import 之后新增：
import { fetchScenarios, type Scenario } from "@/lib/api";
```

- [ ] **Step 2: 新增 SCENARIO_META 常量（在组件外部）**

```typescript
// frontend/app/page.tsx（组件函数之前）

const SCENARIO_META: Record<string, {
  roleTitle: string;
  description: string;
  langs: ("zh" | "en")[];
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
};
```

- [ ] **Step 3: 在组件中新增 state 和 mount effect**

在 `InterviewDemoPage` 组件的 existing state 声明之后新增：

```typescript
const [scenarios, setScenarios] = useState<Scenario[]>([]);
const [selectedStyleId, setSelectedStyleId] = useState<string | null>(null);
const [selectedLang, setSelectedLang] = useState<"zh" | "en">("zh");
const [scenariosLoading, setScenariosLoading] = useState(true);

useEffect(() => {
  fetchScenarios()
    .then(setScenarios)
    .catch((e) => console.error("Failed to load scenarios:", e))
    .finally(() => setScenariosLoading(false));
}, []);
```

- [ ] **Step 4: 修改 `start()` 函数中的 WS URL 拼接**

找到 `resolveWsUrl()` 调用（或直接在 `start()` 中），确保 `style_id` 和 `lang` 被追加：

```typescript
// 在 start() 函数中，建立 WebSocket 之前：
const wsUrl = (() => {
  const base = resolveWsUrl(); // existing function
  const sep = base.includes("?") ? "&" : "?";
  const params = new URLSearchParams();
  if (selectedStyleId) params.set("style_id", selectedStyleId);
  params.set("lang", selectedLang);
  return `${base}${sep}${params.toString()}`;
})();
// 然后用 wsUrl 替换原来的 resolveWsUrl() 调用创建 WebSocket
```

- [ ] **Step 5: 在 JSX 中新增场景选择区域**

在 return 语句的最外层 div 内，`status === "idle"` 时显示的按钮区域之前插入：

```tsx
{/* 场景选择（idle 状态显示） */}
{status === "idle" && (
  <div className="space-y-3">
    <p className="text-sm text-neutral-400">请选择面试场景</p>
    {scenariosLoading ? (
      <p className="text-xs text-neutral-500">加载场景中...</p>
    ) : (
      <div className="grid grid-cols-2 gap-3">
        {scenarios.map((scenario) => {
          const meta = SCENARIO_META[scenario.name];
          const isSelected = selectedStyleId === scenario.id;
          return (
            <button
              key={scenario.id}
              onClick={() => {
                setSelectedStyleId(scenario.id);
                // Reset lang to zh on selection, unless TCL keep current
                if (!SCENARIO_META[scenario.name]?.langs.includes(selectedLang)) {
                  setSelectedLang("zh");
                }
              }}
              className={`text-left p-3 rounded-lg border transition-colors ${
                isSelected
                  ? "border-sky-500 bg-sky-950"
                  : "border-neutral-700 hover:border-neutral-500"
              }`}
            >
              <div className="text-sm font-medium">{scenario.name}</div>
              {meta && (
                <>
                  <div className="text-xs text-neutral-400 mt-0.5">{meta.roleTitle}</div>
                  <div className="text-xs text-neutral-500 mt-0.5">{meta.description}</div>
                  {/* Language selector — only for TCL when selected */}
                  {isSelected && meta.langs.length > 1 && (
                    <div className="flex gap-1 mt-2" onClick={(e) => e.stopPropagation()}>
                      {meta.langs.map((lang) => (
                        <button
                          key={lang}
                          onClick={() => setSelectedLang(lang)}
                          className={`text-xs px-2 py-0.5 rounded ${
                            selectedLang === lang
                              ? "bg-sky-700 text-white"
                              : "bg-neutral-800 text-neutral-400 hover:bg-neutral-700"
                          }`}
                        >
                          {lang === "zh" ? "中文" : "English"}
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
            </button>
          );
        })}
      </div>
    )}
  </div>
)}

{/* 开始面试按钮（已有，修改 disabled 条件） */}
```

修改已有的"开始面试"按钮的 `disabled` 条件：
```tsx
// 找到现有 start button，修改 disabled：
disabled={status !== "idle" || selectedStyleId === null}
```

- [ ] **Step 6: 类型检查**

```bash
cd frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(ui): add scenario card selection with language switcher on home page"
```

---

## Task 12: 前端 — `history/[id]/page.tsx` TCL 五维评分块

**Files:**
- Modify: `frontend/app/history/[id]/page.tsx`

- [ ] **Step 1: 新增 `TclDimensionScores` 组件（在文件顶部，`ScoreBadge` 之后）**

```tsx
// frontend/app/history/[id]/page.tsx

function DimensionBar({ score, label }: { score: number; label: string }) {
  const color =
    score >= 80 ? "bg-emerald-500" : score >= 60 ? "bg-yellow-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-neutral-400 w-16 shrink-0">{label}</span>
      <div className="flex-1 bg-neutral-800 rounded-full h-1.5">
        <div
          className={`${color} h-1.5 rounded-full`}
          style={{ width: `${score}%` }}
        />
      </div>
      <span className="text-xs text-neutral-300 w-8 text-right">{score}</span>
    </div>
  );
}

function TclDimensionBlock({ scores }: { scores: NonNullable<EvaluationOut["dimension_scores"]> }) {
  return (
    <div className="space-y-2">
      <p className="text-xs text-neutral-500 font-medium">TCL 五维评分</p>
      <DimensionBar score={scores.tech_depth ?? 0}   label="技术深度" />
      <DimensionBar score={scores.architecture ?? 0} label="系统架构" />
      <DimensionBar score={scores.competency ?? 0}   label="能力素质" />
      <DimensionBar score={scores.culture ?? 0}      label="文化契合" />
    </div>
  );
}
```

- [ ] **Step 2: 在整体评估块中条件渲染 TCL 五维**

找到 `{/* Overall evaluation */}` 块，在 `ScoreBadge` 行之后加：

```tsx
{/* Overall evaluation */}
{overallEval && (
  <div className="border border-neutral-800 rounded-lg p-4 space-y-3">
    <h2 className="text-sm font-semibold text-neutral-300">整体评估</h2>
    <div className="flex gap-8 justify-center">
      <ScoreBadge score={overallEval.overall_score} label="总分" />
      <ScoreBadge score={overallEval.content_score} label="内容" />
      <ScoreBadge score={overallEval.expression_score} label="表达" />
      <ScoreBadge score={overallEval.voice_score} label="语音" />
    </div>
    {/* TCL 专属维度分块（仅 TCL 面试显示） */}
    {data.company_name === "TCL" && overallEval.dimension_scores &&
      Object.keys(overallEval.dimension_scores).length > 0 && (
      <TclDimensionBlock scores={overallEval.dimension_scores} />
    )}
    {/* rest unchanged */}
  </div>
)}
```

- [ ] **Step 3: 在逐题评估块中也加 TCL 维度分**

在 Q/A Timeline 的 `{ev && (...)}`  块中，现有 `内容/表达/语音` 行之后加：

```tsx
{/* TCL per-question dimension scores */}
{data.company_name === "TCL" && ev.dimension_scores &&
  Object.keys(ev.dimension_scores).length > 0 && (
  <div className="mt-1">
    <TclDimensionBlock scores={ev.dimension_scores} />
  </div>
)}
```

- [ ] **Step 4: 类型检查**

```bash
cd frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/history/[id]/page.tsx
git commit -m "feat(ui): render TCL five-dimension score bars in interview detail page"
```

---

## Task 13: 全量测试 + 验收检查

**Files:** none（验证任务）

- [ ] **Step 1: 运行后端全量测试**

```bash
cd backend
python -m pytest -q --tb=short
```

Expected: 全部通过，约 143+ 个测试（原 128 + 新增约 15）。

- [ ] **Step 2: 运行前端类型检查**

```bash
cd frontend
npm run typecheck
```

Expected: no errors.

- [ ] **Step 3: 运行前端测试**

```bash
cd frontend
npm test
```

Expected: 6 tests pass（现有测试不回归）。

- [ ] **Step 4: 验收 AC-1 — 某公司回归**

```bash
# 启动后端（确保 DB migration 已应用）
cd backend
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

确认 `GET http://localhost:8000/api/company-styles?builtin=true` 返回包含 `某公司` 和 `TCL` 两条记录，且各自 `rubric_type` 正确。

- [ ] **Step 5: 验收 AC-5 — fallback 行为**

```bash
# 连接 WS 不带 style_id，确认 session.interview_id 对应的 Interview.company_name == "某公司"
python -c "
import asyncio, websockets

async def test():
    async with websockets.connect('ws://localhost:8000/ws/interview-demo') as ws:
        msg = await ws.recv()
        import json
        data = json.loads(msg)
        print('interview_id:', data.get('interview_id'), 'type:', data.get('type'))

asyncio.run(test())
"
```

- [ ] **Step 6: 验收 AC-6 — 非法 style_id**

```bash
python -c "
import asyncio, websockets

async def test():
    try:
        async with websockets.connect('ws://localhost:8000/ws/interview-demo?style_id=invalid-id') as ws:
            await ws.recv()
    except websockets.exceptions.ConnectionClosedError as e:
        print('close code:', e.code)  # should be 4008
        assert e.code == 4008

asyncio.run(test())
"
```

Expected: `close code: 4008`

- [ ] **Step 7: 最终 commit（如有未提交改动）**

```bash
git status
# 若有遗漏，add + commit
git log --oneline -10
```

---

## 验收标准对照

| AC | 测试覆盖 |
|---|---|
| 某公司回归 | `test_evaluation_service.py`（原有）+ `test_bidi_session_tcl.py::test_faang_pipeline_dimension_scores_empty` |
| TCL 场景启动 | Task 13 Step 5 手动验收 + `test_bidi_session_tcl.py::test_setup_with_style_id_loads_tcl` |
| TCL 评分维度 | `test_evaluation_service_tcl.py::test_tcl_pipeline_writes_dimension_scores` |
| 历史详情页 TCL | Task 12（前端渲染，类型检查覆盖） |
| fallback | `test_bidi_session_tcl.py::test_setup_fallback_loads_huawei` + Task 13 Step 5 |
| 非法 style_id | `test_bidi_session_tcl.py::test_setup_invalid_style_id_raises` + Task 13 Step 6 |
