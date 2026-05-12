"""Seed data: Company-specific style + Hardware RF Engineer Intern role.

Based on:
- docs/Company Recruitment Process reference
- Job posting: 硬件技术工程师(射频技术方向)实习生, ICT BG 无线网络产品线
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CompanyStyle

COMPANY_STYLE = {
    "name": "H公司",
    "interviewer_style_tags": [
        "以客户为中心",
        "奋斗者为本",
        "自我批判",
        "STAR 行为面试",
        "结构化严谨",
    ],
    "preferred_question_types": [
        "技术深度（专业基础 + 项目细节）",
        "STAR 行为面试（四大维度）",
        "价值观匹配（客户导向 / 奋斗精神 / 自我批判）",
        "岗位技术专项（射频/电路/通信等硬件方向）",
        "职业规划与动机",
    ],
    "sample_questions": [
        # 技术深度（硬件射频方向，针对实习岗）
        "请介绍你做过的一个射频电路或天线设计项目，从需求到验证的完整流程。",
        "射频电路设计中，阻抗匹配为什么重要？你通常用什么方法实现？",
        "滤波器设计有哪些常见拓扑结构（LC / 腔体 / 声表）？各自的适用场景？",
        # 问题解决与决策
        "描述一次你调试硬件电路遇到棘手问题的经历，你是如何定位根因的？",
        "如果测试结果与仿真偏差较大，你的排查思路是什么？",
        # STAR 行为面试 — H公司核心
        "请讲一次你在项目中主动承担超出职责范围的事情，最终结果如何？（客户导向 / 奋斗精神）",
        "描述一次你与同事在技术方案上产生严重分歧的经历，你是如何处理的？",
        "讲一个你因压力大时间紧而完成的项目，过程中有哪些取舍？（奋斗精神）",
        "举一个你从失败或负面反馈中学到东西的例子。（自我批判）",
        # 文化契合 & HR
        "你为什么想加入H公司？对H公司的业务和文化了解多少？",
        "你对未来 3-5 年的职业规划是什么？如何与H公司岗位发展路径结合？",
    ],
    "prompt_context_text": (
        "H公司面试评估体系围绕四大核心维度展开：\n"
        "1. 技术深度与广度：专业基础 + 项目实践 + 调试/分析能力；\n"
        "2. 问题解决与决策：面对复杂问题的分析路径、定位根因的方法论；\n"
        "3. 沟通与人际协作：清晰表达、跨团队协作、建设性冲突解决；\n"
        "4. 文化契合与价值观：以客户为中心、以奋斗者为本、持续自我批判。\n\n"
        "面试风格特点：\n"
        "- 结构化严谨：技术面深挖细节到参数/数据级；追问到底直到理解真实水平；\n"
        "- STAR 行为面试是终面（主管面）的核心工具，要求 Situation/Task/Action/Result 四要素完整；\n"
        "- 文化匹配优先于能力：'先看价值观、再看能力' 的选人哲学；\n"
        "- 不接受空话套话，喜欢 '我主导' 胜于 '团队一起'；\n"
        "- 自我批判维度：面试官会特别观察候选人对自身不足的反思深度。\n\n"
        "评估关键词：客户导向、奋斗文化、持续改进、自我批判、结构化思维、数据支撑。\n\n"
        "对于硬件/射频实习岗，重点考察：\n"
        "- 专业基础：微波网络、电磁场、天线理论、电路分析；\n"
        "- 工程实践：仿真工具（ADS / HFSS / CST）、测试仪器（网分 / 频谱仪）使用经验；\n"
        "- 项目经历：哪怕是课设/毕设，也要能讲清楚设计思路、遇到的坑和解决方法。"
    ),
}


# Default role for MVP (can be extended later with more roles)
DEFAULT_ROLES = [
    {
        "title": "硬件技术工程师（射频技术方向）实习生",
        "business_unit": "ICT BG 无线网络产品线",
        "locations": ["北京", "上海", "深圳", "东莞", "杭州", "苏州", "武汉", "成都", "南京", "西安"],
        "responsibilities": [
            "承担射频硬件的方案设计、产品开发、测试验证，包含收发信机中的射频电路、多形态滤波器、天线等",
            "承担新一代无线通信射频硬件技术的开发工作，根据客户及产品需求，进行新电路、新器件的分析、设计开发、测试验证",
        ],
        "requirements": [
            "微波网络、电子电路、天线、通信、机械等相关专业",
            "具备射频硬件电路、功放、天线、滤波器的开发及调试经验",
        ],
        "business_context": (
            "数字化、智能化与低碳化是未来发展的核心趋势，联接则是现代社会的基石。"
            "H公司无线致力于构建 AI 原生的智联基座，依托 5G 及 5G-A 技术，"
            "赋能 XR/VR、物联网、智能制造及车联网等新兴场景。"
            "部门持续加大在 AI、算法、硬件及软件等领域的投入，"
            "将大模型、智能体及数字孪生等前沿技术深度融入通信系统。"
        ),
    }
]


async def seed_if_empty(session: AsyncSession) -> int:
    """Insert company style if company_style table is empty. Returns count inserted."""
    existing = await session.scalar(select(CompanyStyle).where(CompanyStyle.is_builtin == True))  # noqa: E712
    if existing is not None:
        return 0
    session.add(CompanyStyle(is_builtin=True, **COMPANY_STYLE))
    await session.commit()
    return 1
