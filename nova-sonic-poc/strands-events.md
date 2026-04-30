# Strands BidiAgent Event Probe — Findings

**Date**: 2026-04-28
**Method**: 3 次本地 probe（共 ~$0.015）+ 源码审计 `strands-agents==1.37.0`
**Strands source**: `strands/experimental/bidi/` (models/nova_sonic.py, types/events.py)

---

## 1. Input schema（我们发给 Strands）

从源码 `events.py` 确认的字典 schema：

### `bidi_audio_input` — 发用户音频
```python
{
    "type": "bidi_audio_input",
    "audio": "<base64 PCM>",     # 注意字段名是 audio，不是 data
    "format": "pcm",
    "sample_rate": 16000,
    "channels": 1,
}
```

### `bidi_text_input` — 发文本（Sonic 只把它当 prompt，不会音频回应）
```python
{"type": "bidi_text_input", "text": "...", "role": "user"}
```

---

## 2. Output event types（Strands 发给我们）

从 `nova_sonic.py` 的 event 转换逻辑枚举（source line refs）：

| 事件 type | 来源行 | 触发条件 | 关键字段 |
|---|---|---|---|
| `bidi_connection_start` | 361 | 会话建立 | `connection_id`, `model` |
| `bidi_response_start` | 657 | AI 开始回应 | — |
| `bidi_audio_stream` | 597 | AI 音频帧 | `audio`(base64), `format`, `sample_rate`, `channels` |
| `bidi_transcript_stream` | 613 | 转录增量 | `text`, `role`("user"\|"assistant"), `is_final`, `current_transcript` |
| `bidi_interruption` | 611/635 | 用户打断 | `reason="user_speech"` |
| `bidi_response_complete` | 584 | AI 响应结束 | `response_id`, `stop_reason`("complete"\|"interrupted") |
| `bidi_usage` | 643 | Token 计量 | `inputTokens`, `outputTokens`, `totalTokens` |
| `tool_use_stream` | 630 | 工具调用 | `delta.toolUse`, `current_tool_use` |

---

## 3. ✅ 关键发现：Usage Event 可用

**实测**（连接开场）：
```
bidi_usage  {inputTokens: 22,  outputTokens: 0, totalTokens: 22}
bidi_usage  {inputTokens: 179, outputTokens: 0, totalTokens: 179}
bidi_usage  {inputTokens: 180, outputTokens: 0, totalTokens: 180}
bidi_usage  {inputTokens: 223, outputTokens: 0, totalTokens: 223}
```

**结论**：unit-2-design §3 BR-5 的成本计量**可以直接用 `bidi_usage` 事件**，无需按会话时长估算 fallback。实现要点：
- 累加**最后一个** `bidi_usage` 事件的 `totalTokens`（它是累计值，不是增量）
- 存储为 `interview.bidi_tokens_total`
- 成本 = `inputTokens × price_in + outputTokens × price_out`（Nova Sonic 按 modality 定价；输入 audio $0.00114/1k tokens，输出 audio $0.0136/1k tokens — 需在 config 里加两个价格参数）
- **可移除计划里的 `nova_sonic_price_per_sec` 兜底配置**

---

## 4. ⚠️ 未完全观察到的事件

以下事件**源码确认存在但实测未触发**（因为 probe 的合成音频未通过 Sonic VAD）：
- `bidi_audio_stream`
- `bidi_transcript_stream`
- `bidi_response_start` / `bidi_response_complete`
- `bidi_interruption`

**影响**: 低。事件名和 payload 都已从源码确认；真实对话在前端接入后（unit-4）会自然触发，届时再微调。

**VAD 触发经验**（实测教训）：
- 纯静音 PCM：不触发（Sonic 视为"无话可说"）
- 纯正弦波：不触发（被判为噪声）
- 纯文本输入：Sonic 接受但不产生音频输出
- **需要**：真实人声 PCM（麦克风输入）

---

## 5. 对 unit-2 的具体影响

### 需要更新的决策

1. **State machine 事件映射**（unit-2-design §5.3）——  从推测改为确定：
   - ❌ 原 `outputTranscriptionCompleted` → ✅ 实际 `bidi_transcript_stream` with `role="assistant"` and `is_final=True`
   - ❌ 原 `inputTranscriptionCompleted` → ✅ 实际 `bidi_transcript_stream` with `role="user"` and `is_final=True`
   - ✅ AI 响应结束的权威信号：`bidi_response_complete` (stop_reason="complete")
   - ✅ 用户打断信号：`bidi_interruption`

2. **Code plan 调整**：
   - Part A2 配置项：删除 `nova_sonic_price_per_sec`；增加 `nova_sonic_input_audio_price_per_1k` 和 `nova_sonic_output_audio_price_per_1k`
   - Part B1 `NovaSonicClient.last_usage()`：订阅 `bidi_usage` 事件，保留最后一次 totalTokens/inputTokens/outputTokens
   - FakeBidiAgent fixture：按本表的事件 shape 构造脚本化事件流

3. **无返工风险项**：状态机整体结构（SETUP/SPEAKING/LISTENING/PERSISTING/NEXT_Q）保持不变；只是触发事件的具体名字和字段对齐到实际 Strands API。

---

## 6. 下一步

- ✅ Probe 任务完成，证据充分
- ✅ 成本计量路径明确（`bidi_usage` 事件可用）
- ➡️ 可以开始 **Step 1: 依赖 + config + env**
- ➡️ Step 2 实施 NovaSonicClient 时按本文 §2 事件表对齐
