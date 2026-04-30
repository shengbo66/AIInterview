# POC Code Generation Plan — unit-0 evaluation-algorithm

**Date**: 2026-04-25
**Unit**: unit-0 POC
**Goal**: 验证评估算法可行性（US-000 Gate）

---

## 1. Scope

**Only implements the evaluation pipeline**. No UI, no database, no interview flow.

**Input**：已有音频文件（或脚本生成的合成样本） + 问题 + 公司风格配置
**Output**：结构化 JSON 评估报告（符合 functional design Section 4 格式）

---

## 2. File Structure

```
poc/                                  # 工作区根目录下的 POC 实现
├── requirements.txt                  # 依赖清单
├── README.md                         # 使用说明 + 环境变量 + 运行命令
├── config.py                         # AWS region / 模型 ID 配置
├── rubric.py                         # Rubric 定义（6 FAANG checkpoints + 5-level expression + voice weights）
├── prompt_template.py                # Stage 1 + Stage 2 Claude prompt
├── voice_features.py                 # 客观语音特征提取（语速/停顿/填充词）
├── transcribe_client.py              # Amazon Transcribe Call Analytics 封装
├── claude_client.py                  # Amazon Bedrock Claude Sonnet 封装
├── evaluator.py                      # 核心 orchestrator (Stage 1 + Stage 2)
├── sample_generator.py               # Phase 0.1 用：Claude 生成好/中/差脚本 + Polly 合成音频
├── run_poc.py                        # CLI 入口：单场评估
├── run_verification.py               # POC Gate 验证脚本：跑 AC1~AC6
└── .env.example                      # AWS credentials 示例
```

**总代码量预估**：~400-500 行 Python

---

## 3. Tasks Checklist

### Part A: 基础设施
- [x] A1. `requirements.txt` — boto3, pydantic, python-dotenv, pytest
- [x] A2. `config.py` — region/model IDs/Transcribe 参数
- [x] A3. `.env.example` — AWS credentials 模板
- [x] A4. `README.md` — 环境准备、运行方法、AC 验证步骤

### Part B: Rubric 和 Prompt
- [x] B1. `rubric.py` — 6 FAANG checkpoints + expression 5-level + voice 5 指标权重 + 阈值
- [x] B2. `prompt_template.py` — Stage 1 + Stage 2 + sample_generation prompt

### Part C: AWS 服务客户端
- [x] C1. `transcribe_client.py` — Call Analytics 启动 + 轮询 + 结果解析
- [x] C2. `claude_client.py` — Bedrock Claude 调用 + JSON 解析 + 重试 + 成本计算
- [x] (bonus) `utils.py` — pure helpers (parse_json_strict)

### Part D: 核心算法
- [x] D1. `voice_features.py` — 客观指标提取 + 中英分词切换 + voice_score
- [x] D2. `evaluator.py` — Stage 1 + Stage 2 orchestrator + 一致性校验

### Part E: 样本生成（Phase 0.1）
- [x] E1. `sample_generator.py` — Claude 生成脚本 + Polly 合成 + ffmpeg 转 WAV

### Part F: CLI 和验证
- [x] F1. `run_poc.py` — 单场评估 CLI
- [x] F2. `run_verification.py` — AC1-6 自动验证

### Part G: Unit Tests (newly added)
- [x] G1. `tests/test_rubric.py` — 8 tests
- [x] G2. `tests/test_claude_client.py` — 6 tests
- [x] G3. `tests/test_voice_features.py` — 14 tests
- [x] **Total: 28/28 passed, 0.03s**

---

## 4. Key Design Decisions

| 决策 | 选择 | 理由 |
|---|---|---|
| HTTP client | boto3 (synchronous) | POC 不需要 async，简化实现 |
| 配置方式 | 环境变量 + config.py 常量 | MVP 再考虑 YAML |
| 样本生成 | Polly Neural voice (zh-CN + en-US) | 满足 Phase 0.1 合成样本需求 |
| 合成音频格式 | MP3 (Polly) → 转 WAV 16kHz mono 给 Transcribe | Transcribe 需 WAV/FLAC |
| 真实样本（Phase 0.2）| 由用户后续提供或录制，脚本支持 WAV/MP3 输入 | 不阻塞 Phase 0.1 |
| 成本跟踪 | 每次 API 调用累加 `cost_usd` 字段 | AC5 验证需要 |
| 错误处理 | 3 次重试 + 指数退避；失败写 error.json | 避免 POC 频繁手动重跑 |

---

## 5. Environment Dependencies

**AWS services（必须可用）**:
- Bedrock Claude Sonnet (`anthropic.claude-sonnet-4-20250514-v1:0` 或当前可用版本)
- Amazon Transcribe Call Analytics
- Amazon Polly (Neural voices: zh-CN-XiaoxiaoNeural 或 zh-CN-Zhiyu, en-US-Joanna)
- S3 bucket (Transcribe 需要音频存 S3)

**本地工具**:
- Python 3.12+
- ffmpeg (音频格式转换，Polly MP3 → WAV)
- `uv` 或 `pip` + virtualenv

---

## 6. Validation Plan

POC 完成后自动跑 `run_verification.py`：
1. 生成 3 段合成样本（好/中/差，英文先 + 中文后）
2. 对每段跑评估 3 次（检查一致性 AC2）
3. 计算好/中/差总分差（AC1）
4. 正则检查评语是否含客观指标数值（AC3）
5. 记录耗时（AC4）和累计成本（AC5）
6. 输出 10 份样本给人工审（AC6）—— 脚本不自动，打印"请人工审核以下建议是否具体可操作"

---

## 7. Deferred (not in POC)

- ❌ 不实现 Nova Sonic 集成（POC 不需要实时对话）
- ❌ 不实现数据库持久化（结果输出到本地 JSON 文件）
- ❌ 不实现 Web UI（CLI only）
- ❌ 不做性能优化（POC 目标是跑通，不是快）
- ❌ 不实现面试流程（问题 + 音频文件从命令行参数/目录读取）

---

## 8. Approval

**请确认**：
- `approve` — 按此清单 Part 2 实施代码
- `调整` — 指出要改的项
