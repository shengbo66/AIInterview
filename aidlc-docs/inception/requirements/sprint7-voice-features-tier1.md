# Sprint 7 Requirements — voice_features Tier 1 Expansion

**Status**: Draft → Pending Team Review
**Date**: 2026-05-02
**Sprint**: 7 (follow-up to Sprint 6)

## Intent

在 Sprint 6 的 10 个 voice features 基础上，新增 3 个 Tier 1 维度（本地 PCM 可算，无额外 AWS 成本）：

1. **volume_stability** — 声音是否稳定（紧张的人音量忽大忽小）
2. **first_response_delay** — 问完题到开始回答的延迟（反映准备 / 熟悉度）
3. **hesitation_markers** — 拖长音 / 短犹豫停顿次数（反映思考困难）

## Functional Requirements

### FR-1: 3 个新指标计算

| 字段 | 类型 | 含义 | 算法 |
|---|---|---|---|
| `volume_mean` | float | 非静音帧 RMS 平均（线性） | 所有非静音帧 RMS 平均，规范化到 0-1 |
| `volume_stability` | float | 变异系数（0=稳定，>1=不稳） | stddev(帧 RMS) / mean(帧 RMS)，只统计非静音帧 |
| `first_response_delay_sec` | float | 开头静音时长 | 从音频起点到首个非静音帧的时长 |
| `hesitation_count` | int | 短停顿（200-500ms）次数 | RMS 低于阈值且持续 200-500ms 的段数 |

**注意**: `volume_mean` 顺带算出来，供前端展示参考（不进入 voice_score）

### FR-2: voice_score 扩展扣分规则

- **first_response_delay**: > 3s 扣 5, > 5s 扣 10, > 8s 扣 15
- **hesitation_count** (normalized by duration): > 10/min 扣 5, > 20/min 扣 10
- **volume_stability**: > 0.6 扣 5, > 1.0 扣 10

**总上限**: 所有维度叠加后下限仍 clamp 到 0-100（已有逻辑）

### FR-3: VoiceFeatures dataclass 加字段，_DUMMY_VOICE 对应更新

### FR-4: 前端详情页 Answer card 扩展展示
- 原：`⚡ 语速 X.X 字/秒 · 停顿 N 次 · 填充词 M 个`
- 新（条件性）：
  - 如果 `first_response_delay_sec > 2`: 追加 `· 首答延迟 X.X秒`
  - 如果 `hesitation_count > 3`: 追加 `· 犹豫 N 次`
  - 如果 `volume_stability > 0.5`: 追加 `· 音量不稳`

## Non-Functional Requirements

- **性能**: 3 个新指标都复用现有帧 RMS 数组，无额外 O(n) loop（加几个聚合统计即可），性能影响 < 10ms
- **向后兼容**: 老数据 voice_features 缺字段 → rubric 读 `.get(field, 0)` 不崩
- **测试**: 每个新字段 ≥ 3 tests（正常/边界/极端）+ voice_score 扣分矩阵扩展测试

## Out of Scope
- Tier 2 (Transcribe) / Tier 3 (ML 模型)
- 音调/语调分析 (pitch)
- 情感分析

## Success Criteria

1. AC-1 `voice_analyzer.analyze()` 返回新 4 字段（volume_mean + volume_stability + first_response_delay_sec + hesitation_count）
2. AC-2 `voice_score_from_features` 考虑 3 个新扣分维度
3. AC-3 tests 全绿：后端 ≥ 93 + 12 新 = 105，前端 ≥ 6 + 1 新
4. AC-4 真实 141s session 重新计算，新字段有合理值
5. AC-5 前端条件性展示（只在值有意义时显示）
6. AC-6 部署 + 无 regression

## Estimation: 30-45 分钟
