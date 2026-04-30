"""Prompt templates for Claude evaluation."""
import json
from .rubric import rubric_markdown


def stage1_prompt(
    question: str,
    transcript: str,
    voice_features: dict,
    company: str,
    role: str,
    language: str,
    style_tags: list[str] | None = None,
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
{rubric_markdown()}

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


def stage2_prompt(per_question_results: list[dict]) -> str:
    results_json = json.dumps(per_question_results, ensure_ascii=False, indent=2)
    return f"""你是面试教练。基于下面 N 道题的逐题评估结果，生成整场面试的整体报告。

## 逐题结果
{results_json}

## 输出格式（严格 JSON）
{{
  "overall_content_score": <加权均值>,
  "overall_expression_score": <...>,
  "overall_voice_score": <...>,
  "overall_score": <content*0.5 + expression*0.3 + voice*0.2>,
  "overall_result": "Pass" or "Borderline" or "No-Pass",
  "overall_summary": "2-3 句整体评价",
  "strengths": ["优点 1", "优点 2"],
  "top_3_improvement_priorities": ["影响最大的改进 1", "...", "..."]
}}
"""


def sample_generation_prompt(quality: str, language: str, question: str) -> str:
    """Prompt for Claude to generate good/medium/poor sample answers."""
    quality_desc = {
        "good": "优秀候选人：STAR 结构完整、有具体数据、表达清晰、逻辑严密、展现主动性",
        "medium": "中等候选人：基本回答了问题，但缺乏具体细节、结构不完整、有少量冗余",
        "poor": "较差候选人：回答偏离主题或很简短、无 STAR 结构、无具体例子、语言含糊",
    }[quality]
    return f"""你是一个面试脚本生成器。生成一段候选人对下面问题的回答，用于测试评估算法。

语言: {language}
质量要求: {quality_desc}
问题: {question}

输出要求：
- 长度 80-150 词（英文）或 150-250 字（中文）
- 口语化（会被 TTS 朗读）
- 直接输出回答文本，不要 "Here is the answer:" 之类的前缀
- 如果是 poor 质量，可以适当包含填充词如 "嗯/um/就是"
- 只输出候选人说的话，不要包括面试官的话
"""
