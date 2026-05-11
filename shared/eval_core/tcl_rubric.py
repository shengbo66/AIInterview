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

_TECH_DEPTH_KEYS = {"tech_depth_knowledge", "tech_depth_impl"}
_ARCH_KEYS = {"arch_e2e_design", "arch_integration"}
_COMPETENCY_KEYS = {"tcl_competency_star"}
_CULTURE_KEYS = {"tcl_culture_fit"}

_TECH_DEPTH_W = 35
_ARCH_W = 25
_COMPETENCY_W = 20
_CULTURE_W = 10


def tcl_rubric_markdown() -> str:
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
    if not keys:
        return 0.0
    passed = sum(1 for k in keys if checkpoints.get(k, {}).get("result") == "Pass")
    return passed / len(keys)


def tcl_content_score(checkpoints: dict) -> tuple[int, int, dict]:
    """Return (content_score, expression_score, dimension_scores).

    content_score = (tech_depth*35 + arch*25) / 60 * 100
    expression_score = (competency*20 + culture*10) / 30 * 100
    dimension_scores = {tech_depth, architecture, competency, culture} each 0-100
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
