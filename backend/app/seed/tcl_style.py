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
