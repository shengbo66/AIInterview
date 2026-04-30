# POC — Evaluation Algorithm

验证评估算法可行性（US-000 Phase 0 Gate）。使用 Amazon Transcribe Call Analytics + Bedrock Claude Sonnet。

## Prerequisites

- Python 3.12+
- AWS credentials 配置完成，且 IAM 具备：
  - `bedrock:InvokeModel` (Claude Sonnet)
  - `transcribe:StartCallAnalyticsJob`, `transcribe:GetCallAnalyticsJob`
  - `polly:SynthesizeSpeech`
  - `s3:PutObject`, `s3:GetObject` (POC bucket)
- S3 bucket 已创建（默认 `interviewer-poc-audio`）
- `ffmpeg` 本地可用（Polly MP3 → WAV 转换）

## Setup

```bash
cd poc
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 AWS_REGION 和 POC_S3_BUCKET
```

## Run

### 单场评估
```bash
python run_poc.py --audio samples/sample-good.wav --question "Tell me about a team conflict" --company ByteDance --role "Backend Engineer" --language en
```

### Phase 0.1 合成样本生成 + 验证
```bash
# 1. 生成好/中/差三段合成样本
python sample_generator.py --language en --out samples/

# 2. 跑 Phase 0.1 Gate 验证（6 AC）
python run_verification.py --samples-dir samples/
```

输出：`results/` 下每份样本的评估 JSON + `results/verdict.md` Gate 报告。

## Gate Acceptance Criteria (US-000)

1. 好/中/差三级样本总分差 ≥ 15
2. 同样本 3 次运行方差 ≤ 5
3. 评语含至少 1 个客观指标数值
4. 单场评估 ≤ 30 秒
5. 单场成本 ≤ $4
6. 10 份样本人工审核 ≥ 8 份建议可操作

## Files

- `config.py` / `rubric.py` / `prompt_template.py` — 配置和 rubric
- `transcribe_client.py` / `claude_client.py` — AWS 封装
- `voice_features.py` — 客观语音指标提取
- `evaluator.py` — 核心评估 orchestrator
- `sample_generator.py` — 合成样本生成
- `run_poc.py` / `run_verification.py` — CLI
