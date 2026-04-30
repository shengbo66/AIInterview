# Functional Design — unit-0 POC: Evaluation Algorithm

**Unit**: unit-0 (Phase 0 POC)
**Stories**: US-000
**Date**: 2026-04-25

---

## 1. Algorithm Overview

```
Input: audio_file_path, question_text, company_style (optional)
       │
       ├──→ [Step 1] Transcribe Call Analytics
       │     Output: transcript, sentiment, talk_speed,
       │             silence_events, interruptions
       │
       ├──→ [Step 2] Extract Additional Features (Python)
       │     Output: filler_word_count, filler_word_ratio,
       │             word_count, speaking_ratio
       │
       ├──→ [Step 3] Stage 1 — Per-Question Claude Evaluation
       │     Input: question + transcript + voice_features + rubric
       │     Output: {content, expression, voice} scores +
       │             suggestions + ideal_answer
       │
       └──→ [Step 4] Stage 2 — Overall Claude Evaluation (if multi-Q)
             Input: all per-question results
             Output: overall_score + weighted aggregate +
                     top 3 improvement priorities

Output: EvaluationReport (JSON)
```

---

## 2. Rubric Definition (Two-Layer: Pass/No-Pass + Numeric Score)

**Design rationale** (community-informed, see `references-and-evolution.md`): zixi-liu/interview-ai-prototype 验证过的做法是**Pass/No-Pass checkpoint** 而不是纯数字打分，对用户更直观。我们采用**两层输出**：
- **给用户看**：Pass/No-Pass/Borderline + checkpoint reasoning（直观）
- **内部存储/图表**：0-100 数字分数（用于雷达图、趋势追踪）

### 2.1 Content Dimension — FAANG Checkpoint 细化（6 checkpoints）

借鉴 FAANG 行为面试标准。每个 checkpoint 独立评判 Pass/No-Pass：

| Checkpoint | 评判标准 |
|---|---|
| **STAR Method Structure** | 是否有 Situation / Task / Action / Result 四要素 |
| **Specificity & Details** | 是否有具体事例、数据、指标 |
| **Impact & Results** | 是否清晰展示可量化的影响/结果 |
| **Leadership & Ownership** | 是否体现个人主导/主动担当 |
| **Problem-Solving** | 解决问题的思路是否清晰 |
| **Communication Clarity** | 表达是否结构化、易于跟随 |

**content_score 计算**:
- `pass_count = checkpoints 中 Pass 数量` (0-6)
- `content_score = round(pass_count / 6 * 100)`
- 6/6 = 100, 5/6 = 83, 4/6 = 67, 3/6 = 50, 2/6 = 33, 1/6 = 17, 0/6 = 0

### 2.2 Expression Dimension — 5 级（保持）

| Level | Score | Description |
|---|---|---|
| 1 | 0-20 | 表达混乱、缺逻辑 |
| 2 | 21-40 | 基本可理解但缺结构 |
| 3 | 41-60 | 逻辑基本清晰 |
| 4 | 61-80 | 结构化表达、重点突出 |
| 5 | 81-100 | 开门见山 + 分点清晰 + 呼应问题 |

### 2.3 Voice Dimension — 客观指标加权（保持）

**基于客观指标 + Transcribe Call Analytics sentiment**

| 指标 | 权重 | 评分规则 |
|---|---|---|
| **Talk Speed**（词/秒）| 25% | 2.5-4 wps = 优秀；<2 或 >5 扣分 |
| **Pause Frequency**（停顿次数/分）| 20% | 3-8 次/分 = 自然；>15 次或无停顿扣分 |
| **Filler Word Ratio** | 20% | <3% = 优秀；>8% 扣分 |
| **Speaking Ratio**（说话时长/总时长）| 15% | >70% = 流畅；<40% 扣分 |
| **Sentiment (Transcribe)** | 20% | POSITIVE/NEUTRAL 加分；NEGATIVE + high confidence 扣分 |

**voice_score 计算**：各指标加权平均 → 映射到 0-100

### 2.4 Overall Result (Presentation Layer)

基于 `overall_score`（content 50% + expression 30% + voice 20%）：

| Numeric Range | Presentation Label |
|---|---|
| ≥ 75 | **Pass** |
| 50 - 74 | **Borderline** |
| < 50 | **No-Pass** |

用户看到 Label + 改进建议；内部仍保存数字。

---

## 3. Voice Features Schema

```json
{
  "duration_total_sec": 92.3,
  "duration_speaking_sec": 78.5,
  "speaking_ratio": 0.85,
  "word_count": 245,
  "talk_speed_wps": 3.12,
  "pause_count": 5,
  "pause_count_per_minute": 3.24,
  "avg_pause_sec": 1.2,
  "longest_pause_sec": 3.8,
  "filler_words_detected": ["嗯", "就是", "这个"],
  "filler_word_count": 7,
  "filler_word_ratio": 0.029,
  "transcribe_sentiment": {
    "overall": "NEUTRAL",
    "positive_ratio": 0.4,
    "neutral_ratio": 0.5,
    "negative_ratio": 0.1
  },
  "interruptions": 0
}
```

---

## 4. Claude Evaluation Prompt Template (Stage 1)

```
你是一位专业的面试教练，针对{company_name}（风格：{style_tags}）{role_title}岗位进行面试评估。

## 评估任务
针对下面的面试问题和候选人回答，按 FAANG 行为面试标准评估，并在三个维度给出评分。

## 问题
{question_text}

## 候选人回答（转录）
{transcript}

## 客观语音指标
- 回答总时长: {duration_total_sec}s
- 语速: {talk_speed_wps} 词/秒
- 停顿次数: {pause_count} 次 ({pause_count_per_minute} 次/分钟)
- 最长停顿: {longest_pause_sec}s
- 填充词占比: {filler_word_ratio:.1%} （检测到: {filler_words_detected}）
- 情感倾向: {transcribe_sentiment.overall}

## 评分 rubric
{rubric_markdown}

## 输出格式（严格 JSON，不要任何额外文本）
{
  "content_checkpoints": {
    "star_structure": {"result": "Pass" | "No-Pass", "reason": "具体理由"},
    "specificity_details": {"result": "Pass" | "No-Pass", "reason": "..."},
    "impact_results": {"result": "Pass" | "No-Pass", "reason": "..."},
    "leadership_ownership": {"result": "Pass" | "No-Pass", "reason": "..."},
    "problem_solving": {"result": "Pass" | "No-Pass", "reason": "..."},
    "communication_clarity": {"result": "Pass" | "No-Pass", "reason": "..."}
  },
  "content_score": <0-100，由 pass 数量换算>,
  "expression_score": <0-100，5 级 rubric>,
  "expression_reasoning": "具体理由",
  "voice_score": <0-100，由客观指标加权>,
  "voice_reasoning": "必须引用至少 1 个客观指标数值（语速/停顿/填充词/情感）",
  "overall_score": <content*0.5 + expression*0.3 + voice*0.2>,
  "overall_result": "Pass" | "Borderline" | "No-Pass",
  "improvement_suggestions": [
    "具体可操作的建议 1（引用原回答片段或指标）",
    "具体可操作的建议 2",
    "具体可操作的建议 3"
  ],
  "ideal_answer": "一段符合 {company_name} 风格、STAR 结构完整的参考答案（3-5 句）"
}
```

**规则**：
- 温度 0.3（稳定性优先，但保留一定解释弹性）
- max_tokens: 2500（因新增 checkpoints 结构）
- Response format: JSON object

---

## 5. Claude Evaluation Prompt Template (Stage 2 — Overall)

```
你是面试教练。基于下面 N 道题的逐题评估结果，生成整场面试的整体报告。

## 逐题结果
{per_question_results_json}

## 输出格式（严格 JSON）
{
  "overall_content_score": <加权均值，可微调>,
  "overall_expression_score": <...>,
  "overall_voice_score": <...>,
  "overall_score": <三维加权：content 50% + expression 30% + voice 20%>,
  "overall_summary": "2-3 句整体评价",
  "strengths": ["优点 1", "优点 2"],
  "top_3_improvement_priorities": [
    "优先改进项 1（影响最大）",
    "...",
    "..."
  ]
}
```

**权重设计**：内容 50%、表达 30%、语音 20% —— 面试最重要的仍是内容。

---

## 6. Pseudo-Code Flow

```python
def evaluate_interview(audio_files, questions, company_style) -> EvaluationReport:
    per_question = []
    cost_usd = 0.0
    
    for audio, q in zip(audio_files, questions):
        # Step 1: Transcribe
        tca_result = transcribe_call_analytics(audio, language=q.language)
        cost_usd += tca_cost(duration=tca_result.duration)
        
        # Step 2: Extract features
        voice_features = extract_voice_features(
            transcript=tca_result.transcript,
            segments=tca_result.segments,
            sentiment=tca_result.sentiment,
        )
        
        # Step 3: Stage 1 evaluation
        stage1 = claude_evaluate_stage1(
            question=q.text,
            transcript=tca_result.transcript,
            voice_features=voice_features,
            company_style=company_style,
            rubric=load_rubric(),
        )
        cost_usd += claude_cost(stage1.tokens)
        per_question.append(stage1)
    
    # Step 4: Stage 2 overall
    stage2 = claude_evaluate_stage2(per_question)
    cost_usd += claude_cost(stage2.tokens)
    
    return EvaluationReport(
        per_question=per_question,
        overall=stage2,
        voice_features_list=[...],
        total_cost_usd=cost_usd,
        rubric_version="v1.0",
    )
```

---

## 7. Edge Cases

| Case | Handling |
|---|---|
| Transcribe 失败 | 重试 2 次；最终失败 → EvaluationReport 标记为 failed + 错误信息 |
| Transcribe 返回空 transcript（用户没说话）| 给出 content=0, voice=0, reasoning="未检测到有效回答" |
| Claude 返回非 JSON | 重试 1 次（可微调 prompt）；仍失败 → evaluation failed |
| 单题音频 <5 秒 | 仍评估但 flag "too_short"，提示在评语中 |
| 语速计算（词/秒）中文如何算字？ | 中文按"字数"（汉字 char count），英文按 word（空格分词）；脚本按 language 参数切换 |
| 填充词检测 | 中文: 嗯/啊/呃/就是/然后/那个/这个/其实；英文: um/uh/like/you know/I mean |

---

## 8. POC Verification Strategy (maps to US-000 ACs)

| AC | How to Verify |
|---|---|
| 好/中/差三级评分差 ≥ 15 分 | Phase 0.1 跑 3 段合成样本，比较总分 |
| 方差 ≤ 5 分（一致性）| 同一段录音跑 3 次，看三维分数极差 |
| 评语引用 ≥ 1 个客观指标 | 正则匹配评语文本是否含数字 + 指标关键词 |
| 耗时 ≤ 55 秒 | 脚本打印 time.time() 起止 |
| 成本 ≤ $4 | 脚本累计 cost_usd 字段 |
| 建议可操作度 | 人工审 10 份样本 |

---

## 9. What's Out of Scope (for POC)

- ❌ 实时评估（POC 是离线批处理）
- ❌ 面试问答动态生成（POC 问题固定）
- ❌ 多语言完整支持（POC 中英各试一次即可）
- ❌ 错误恢复的用户 UI（POC 是 CLI）
- ❌ 性能优化（POC 单线程即可）
