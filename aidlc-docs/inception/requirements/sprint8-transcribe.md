# Sprint 8 Requirements — Amazon Transcribe + Comprehend 集成

**Status**: Draft → Pending Team Review
**Date**: 2026-05-02
**Sprint**: 8

## Intent

用 Amazon Transcribe 获取 word-level timestamps + confidence，用 Comprehend 获取情感倾向，
增强 voice_features 维度（不替换原有 Nova Sonic transcript）。

## Architecture Decision

**方案 B**: Finalize 时 fire-and-forget 提交 Transcribe jobs，evaluation 启动时等待结果。
- Transcribe async 模式（~30-60s/job）
- 5 个 answer 并行提交，evaluation 时 poll 直到全部完成（最多等 90s）
- 不阻塞 finalize 返回给前端

## Functional Requirements

### FR-1: transcribe_client.py 模块

提供 3 个纯异步函数：

```python
async def submit_job(s3_key: str, language: str = "zh-CN") -> str:
    """Submit Transcribe job. Return job_name for tracking."""

async def get_result(job_name: str) -> dict | None:
    """Return {"status": "COMPLETED"|"IN_PROGRESS"|"FAILED", "words": [...], "transcript": "..."} 
    or None if job not found. Caller decides whether to poll or give up."""

async def parse_words(transcribe_output: dict) -> list[Word]:
    """Parse Transcribe output JSON. Returns list of Word(text, start_ms, end_ms, confidence)."""
```

- S3 input: `s3://{bucket}/{user_audio_s3_key}` (已存在的 user audio)
- Output: 写回 `s3://{bucket}/transcribe-output/{job_name}.json`
- Media format: 显式 `raw` + sample rate 16000 + media encoding `pcm` (s3 里是 raw PCM16)

### FR-2: comprehend_client.py 模块

```python
async def detect_sentiment(text: str, language: str = "zh") -> dict:
    """Return {"overall": "POSITIVE"|"NEGATIVE"|"NEUTRAL"|"MIXED", 
              "scores": {"positive": 0.1, "negative": 0.7, "neutral": 0.1, "mixed": 0.1}}"""
```

### FR-3: voice_analyzer.analyze() 可选入参扩展

```python
def analyze(
    pcm_bytes: bytes,
    sample_rate: int,
    transcript: str,
    words: list[Word] | None = None,  # 新增，可选
    sentiment: dict | None = None,  # 新增，可选
) -> VoiceFeatures:
```

新增 VoiceFeatures 字段：

| 字段 | 来源 | 说明 |
|---|---|---|
| `accurate_wpm` | words list | 基于真实 word timing 的语速 (字/分钟) |
| `accurate_speaking_sec` | words list | sum(word_end - word_start), 精确说话时长 |
| `low_confidence_ratio` | words list | confidence < 0.6 的词 / 总词 |
| `low_confidence_words` | words list | confidence < 0.6 的词文本列表（去重） |
| `sentiment_overall` | sentiment | "POSITIVE"/"NEGATIVE"/"NEUTRAL"/"MIXED"/"UNKNOWN" |
| `sentiment_scores` | sentiment | 4 个分数 dict |

**逻辑**: 
- 如果 `words is None` (老数据或 Transcribe 失败)，新字段用 0/[]/"UNKNOWN" 填充 (fallback)
- PCM-based 现有指标不变（cps/pauses/fillers 等）
- `accurate_wpm` 和 `accurate_speaking_sec` 并列展示，让用户看到"Nova Sonic estimate vs Transcribe actual"

### FR-4: evaluation_service.py 集成

```python
async def _run_pipeline():
    # 1. Load interview + questions + answers
    
    # 2. (NEW) Submit Transcribe jobs for all answers with user_audio_s3_key
    #    - Use asyncio.gather for parallel submission (5 jobs in < 1s)
    
    # 3. (NEW) Wait for Transcribe jobs with timeout (90s per batch max)
    #    - Poll every 5s, give up at 90s and proceed with partial results
    
    # 4. For each Q/A: _compute_voice_features_enhanced(answer, transcribe_result)
    #    - Use Transcribe words if available
    #    - Detect sentiment via Comprehend
    #    - Pass both into voice_analyzer.analyze()
    
    # 5. (unchanged) Run Claude stage1 + stage2 + persist
```

**容错**:
- Transcribe job FAILED → fallback dummy values for Transcribe-based fields
- Comprehend 失败 → sentiment = "UNKNOWN"
- 超时（单 job > 90s） → proceed with PCM-only features

### FR-5: rubric voice_score 扩展

- **low_confidence_ratio > 0.2** (>20% 词听不清) → -10
- **sentiment NEGATIVE** → -5 (消极表达在面试里不利)
- **accurate_wpm 存在时优先**: 用 wpm (中文 150-250/min 理想) 替代 cps 扣分规则
  - accurate_wpm < 100 or > 350 → -15 (extreme)
  - accurate_wpm < 150 or > 280 → -10

### FR-6: 前端详情页扩展

在现有 ⚡ 和 🎚 行后加 📊 行（仅当 Transcribe 有结果时）：

```
📊 精确语速 X WPM · 发音清晰度 X% · 情感 积极/中立/消极
```

## Non-Functional Requirements

- **成本**: 每面试 +$0.01-$0.03（Transcribe $0.024/min × 5 answers × 平均 0.5min + Comprehend 可忽略）
- **延迟**: evaluation 总时长 +60-90s（Transcribe async polling），用户在 finalize 后即返回首页
- **幂等性**: job_name 用 `{interview_id}-{question_id}-{role}` 格式，重复提交复用
- **权限**: IAM role 需加 `transcribe:StartTranscriptionJob`, `transcribe:GetTranscriptionJob`, `comprehend:DetectSentiment`

## Out of Scope

- 替换原 transcript_text（保持 Nova Sonic 输出）
- Custom vocabulary（5G/RF 等术语）— 下一 sprint 再调优
- 实时 Transcribe streaming — 本次只用 async batch
- Speaker diarization（我们只有单候选人）

## Success Criteria

1. **AC-1** transcribe_client + comprehend_client 独立可测（mock boto3）
2. **AC-2** voice_analyzer.analyze 支持 words=None 降级到纯 PCM 分析（向后兼容）
3. **AC-3** rubric voice_score 新维度扣分测试覆盖
4. **AC-4** evaluation_service 真实 141s session 回算，新字段填充合理值
5. **AC-5** Tests 全绿：≥ 105 + 20 新 = 125 pytest
6. **AC-6** 部署 + IAM policy 更新
7. **AC-7** 真实 session 成本 < $0.05

## Estimation: 1.5-2h (complex: IAM + async + job polling)
