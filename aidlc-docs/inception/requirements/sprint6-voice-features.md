# Sprint 6 Requirements — voice_features 本地 PCM 分析

**Status**: **Approved (v1.1 post team review)**
**Author**: AI agent + Robert
**Date**: 2026-05-02
**Sprint**: 6 (first sprint after production deploy)
**Review**: PM (REVISE→RESOLVED) + architect (REVISE→RESOLVED), merged 2026-05-02T10:50

---

## 1. Intent Analysis

**一句话**：把 `evaluation_service.py` 里的 `_DUMMY_VOICE`（全 0 占位）替换成基于用户音频 PCM + transcript 的真实语音特征分析，让 `voice_score` 有意义地参与 `overall_score` 计算（占 20% 权重）。

**用户痛点**：目前面试评估报告的 voice_score 永远是 0，候选人无法从语音维度获得反馈。

---

## 2. Scope (What)

### 2.1 Functional Requirements

**FR-1**: `voice_analyzer` 模块提供纯函数 `analyze(pcm_bytes, sample_rate, transcript)` 返回以下指标：

| 字段 | 类型 | 说明 | 计算方法 |
|---|---|---|---|
| `duration_total_sec` | float | 音频总时长 | `len(pcm) / (sample_rate * 2)` |
| `duration_speaking_sec` | float | 净说话时长 | `duration_total - sum(pauses)` |
| `speaking_ratio` | float 0-1 | 说话占比 | `duration_speaking / duration_total` |
| `talk_speed_cps` | float | 中文字符/秒 | `len(transcript_without_punct) / duration_speaking` |
| `pause_count` | int | 停顿次数（>500ms 静音段） | RMS 检测 |
| `pause_count_per_minute` | float | 每分钟停顿数 | `pause_count / (duration_total / 60)` |
| `longest_pause_sec` | float | 最长停顿 | max(pause lengths) |
| `filler_word_count` | int | 填充词总数 | 正则匹配 transcript |
| `filler_word_ratio` | float 0-1 | 填充词占字数 | `filler_count / total_char_count` |
| `filler_words_detected` | list[str] | 匹配到的填充词列表 | 正则 group |

**FR-2**: `voice_score` 计算公式（新 `rubric.voice_score_from_features`）：
- 基础分 100
- 语速扣分：`cps < 2.5` 扣 15，`cps > 6` 扣 15，区间内 0
- 停顿扣分：`pause_per_min > 15` 扣 10，`> 25` 扣 20
- 填充词扣分：`filler_ratio > 0.08` 扣 15，`> 0.15` 扣 30
- 静音时段扣分：`speaking_ratio < 0.4` 扣 20 (answer 里一大半时间没说话)
- 下限 0，上限 100

**FR-3**: `evaluation_service._run_pipeline` 第 102 行：
- 从 S3 下载 `a.user_audio_s3_key` 对应的 **raw PCM16 LE mono 16kHz** (content_type=`audio/pcm`, 格式与 `bidi_interview_session._user_audio_chunks` 累积的一致)
- 调 `voice_analyzer.analyze(pcm_bytes, sample_rate=16000, transcript=a.transcript_text)` 得到 features
- 把 features 传进 `stage1_prompt` (已支持) + 填入 `Evaluation.voice_features`
- `voice_score = rubric.voice_score_from_features(features)`

**FR-4**: 容错分层（architect review）：
- `user_audio_s3_key is None` (老数据) → fallback to dummy (voice_score=0), log INFO "no audio for Q"
- S3 `NoSuchKey` / `AccessDenied` → fallback + log WARNING
- PCM 长度 < 16000 (1 秒) → fallback + log WARNING "PCM too short"
- `voice_analyzer.analyze` 抛异常 → **raise**（让 evaluation 状态变 `evaluation_failed`，暴露 bug 不掩盖）

**FR-5**: 前端最小展示（PM review 加）：
- 详情页每个 Answer card 底部显示一行：`⚡ 语速 X.X 字/秒 · 停顿 N 次 · 填充词 M 个`
- 值来自 `evaluation.voice_features`
- voice_features 全 0 时显示「暂无语音分析」

### 2.2 Non-Functional Requirements

- **Performance**: 单题 voice analysis < 200ms (对 < 2min PCM)
- **Testability**: `voice_analyzer.analyze` 纯函数，用 `bytes` 生成 PCM fixture 可完全离线测试
- **No new external dependency**：核实后 **numpy 未安装**，改用 **Python stdlib `struct` + 循环**实现（对 2min PCM 纯 Python 跑 < 50ms，满足性能要求）
- **Cost**: 零 AWS 调用（Transcribe 已被排除）
- **Async compatibility**: S3 下载用 `asyncio.to_thread(boto3.get_object)` 保持异步 pipeline（同 s3_audio.py 其他方法的模式）

### 2.3 Out of Scope

- Amazon Transcribe 集成（未来如需 word-level timing 可加）
- 情感分析 (sentiment) — transcribe_sentiment 仍留为 `{"overall": "NEUTRAL"}` 占位
- 实时反馈（面试中显示语速）
- **历史 evaluation 数据**自动重算（老数据仍旧 dummy，可手动触发 `POST /api/interviews/{id}/evaluate` 重算）

### 2.4 User-facing Minimal Display (added after PM review)

- 详情页 Answer card 底部显示一行轻量指标：「⚡ 语速 X 字/秒 · 停顿 N 次 · 填充词 M 个」
- 不做图表/详细解释，只让用户感知功能已落地
- voice_score 数字已在原 UI 显示（通过 overall_score 的组成部分 tooltip）

---

## 3. Success Criteria / Acceptance

1. **AC-1** 单元测试：voice_analyzer 的 10+ cases 覆盖（正常音频、全静音、短音频、只有填充词、超长、边界值）
2. **AC-2** 单元测试：`voice_score_from_features` 覆盖扣分矩阵（4 档 × 3 维度 + 边界）
3. **AC-3** 集成测试：`evaluation_service` 在有 S3 PCM 的 Q/A 上能返回非 0 voice_score
4. **AC-4** 真实回算：用 5-01 15:51 那次 141s session（5 个 answer with audio）跑 evaluation，检查：
   - 每题 voice_features.duration_total_sec > 0
   - 每题 voice_score 在 [1, 100] 之间（不全是 0 也不全是 100）
   - filler_words_detected 至少有一个非空（表示填充词识别工作）
   - **记录 5 个 answer 的 cps 分布**（如果都在扣分区，考虑调整 threshold）
5. **AC-5** 测试全绿：57 pytest（现有）+ 新增 ≥ 15 个 voice_analyzer tests + ≥ 5 个 rubric.voice_score tests
6. **AC-6** 部署：推到 EC2，重启 backend，手动触发 evaluate 一次历史 session 成功
7. **AC-7** 前端：详情页每个 Answer card 底部出现一行 voice 指标；vitest 绿
8. **AC-8**（产品验收）功能发布后，候选人能在详情页看到语速/停顿/填充词三个指标，主观感受"这个反馈对我有帮助" ≥ 70%（Sprint 6.1 用户访谈 3+ 候选人收集）

---

## 4. Key Design Decisions

### DD-1: 本地 PCM 分析（非 Transcribe）
- **为什么**: 零成本、可离线测试、依赖简单
- **Trade-off**: 中文字符速度不如 Transcribe 的 word-level 精确，但 MVP 够用

### DD-2: 停顿检测用 RMS threshold
- 算法: 每 20ms 一帧算 RMS，< threshold 且连续 > 500ms 算一次 pause
- Threshold: 相对阈值 `max(abs(pcm)) * 0.02` (避免背景噪声影响)
- **Trade-off**: 不如 VAD 准，但不引入模型依赖

### DD-3: 填充词清单硬编码
- **中文列表** (参考中文语用学研究 "话语标记语" 常见 filler)：嗯、啊、呃、那个、就是、这个、然后、所以说、对对、是、好、嗯嗯、对、就、嗯哼
- **扩展机制**: 常量列表在 `voice_analyzer.py`，未来如需可配置改成 `company_style.filler_words` 字段（Sprint 6.2+）
- **Trade-off**: 不覆盖所有方言，但第一版够用

### DD-4: voice_score 公式简单扣分制
- **为什么**: 透明可解释，用户能看懂为啥扣分
- **Trade-off**: 不是 ML 模型，但面试评估本来就需要可解释性
- **阈值校准**: 初始阈值基于直觉，**AC-4 真实回算时记录 cps 分布，如果 5 个样本全在扣分区间则调整** (Sprint 6.1 微调)

### DD-5: S3 下载失败分层处理（见 FR-4）
- 不同错误不同处理，避免"一律 fallback"掩盖真 bug

### DD-6: 纯 Python stdlib 实现（不引入 numpy）
- **为什么**: 核实 `pip list` 未装 numpy。新增依赖 ~15MB + 减慢 `uv pip install` ~3s。
- **实现**: `struct.unpack(f'<{n}h', pcm_bytes)` 解出 int16 样本，手写 RMS 循环
- **性能验证**: 2min PCM (1.92M samples, 6000 frames × 320 samples each) 纯 Python < 50ms（目标 200ms 有 4× margin）
- **Trade-off**: 代码稍多一点（~30 行 vs numpy 10 行），但依赖更轻

### DD-7: S3 下载用 `asyncio.to_thread`
- 遵循现有 `s3_audio.py` 模式（`upload` / `presign_get` / `delete_many` 都是 `asyncio.to_thread(sync_boto3_call)`）
- 新增 `s3_audio.download_bytes(key) -> bytes`
- 对 5 个 answer 串行下载 (evaluation 本来就是串行 Claude 调用)，单次 < 200ms 网络，总共 < 1s，不用并发

---

## 5. File Impact

**New files**:
- `backend/app/services/voice_analyzer.py` (~150 lines, stdlib only)
- `backend/tests/test_voice_analyzer.py` (~200 lines)

**Modified**:
- `backend/app/services/evaluation_service.py` (替换第 102 行的 dummy + 调 voice_analyzer + 走 FR-4 容错)
- `backend/app/clients/s3_audio.py` (新增 `download_bytes(key) -> bytes`)
- `shared/eval_core/rubric.py` (添加 `voice_score_from_features`)
- `shared/eval_core/tests/test_rubric.py` (新增 voice_score 测试)
- `backend/tests/test_evaluation_service.py` (更新期望值)
- `frontend/app/history/[id]/page.tsx` (Answer card 底部加 1 行 voice 指标)

## 6. Dependencies / Risks

- **Risk-1**: 141s session 的 S3 PCM 实际格式验证 — **Mitigation**: 核心代码路径 `bidi_interview_session._user_audio_chunks` → `s3_audio.upload(content_type="audio/pcm")` → raw PCM16 LE mono 16kHz ✅ 已核实
- **Risk-2**: Claude stage1 prompt 对真实 voice_features 可能给出与 dummy 不同的分数 — **Mitigation**: 这是期望行为，测试快照里更新基线
- **Risk-3**: 初始 voice_score 阈值可能偏严（AC-4 校准）
- **Dep**: 无新 python package（纯 stdlib）

## 7. Estimation

- voice_analyzer module + tests: 1.5-2h
- rubric.voice_score + tests: 0.5h
- s3_audio.download_bytes: 0.2h
- evaluation_service integration + tests: 1h
- frontend 轻量展示 + vitest: 0.5h
- 部署 + 端到端验证 + AC-4 回算调阈值: 1h
- **总计**: 4.5-6h (buffer 到 6h)
