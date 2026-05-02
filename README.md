# Interviewer v1.0

AI 语音模拟面试平台 — **某公司 · 硬件技术工程师（射频技术方向）实习生**

基于 Amazon Nova Sonic 双向语音流 + Claude 文本评估 + Transcribe 语音分析 + Comprehend 情感分析。

**Demo**: https://d1hlahtkv3v1q6.cloudfront.net  
**Demo 账号**: `demo@interviewer.test` / `Interview2026!`

---

## 功能概览

| 功能 | 说明 | Sprint |
|---|---|---|
| 🎤 实时语音面试 | Nova Sonic 双向流，AI 面试官中文提问 + 追问 | 1-2 |
| 💾 面试持久化 | Q/A 转录 + 音频 S3 存储 + SQLite 记录 | 2 |
| 📊 AI 评估 | Claude 逐题评分（内容/表达/语音）+ 整体评估 | 3 |
| 📜 历史记录 | 面试列表 + 详情页（Q/A 时间线 + 评分 + 改进建议 + 参考答案）| 3 |
| 🔊 音频回放 | 历史详情页播放 AI/用户音频（Web Audio API + PCM16）| 4 |
| 🔐 Cognito 认证 | JWT auth + Hosted UI + 自动 token 刷新 | 5 |
| ☁️ 云部署 | EC2 Tokyo + CloudFront HTTPS + Caddy 反向代理 | 5 |
| 📈 语音特征分析 | 语速/停顿/填充词/首答延迟/犹豫/音量稳定性 (本地 PCM) | 6-7 |
| 🎯 Transcribe 精确分析 | 精确 WPM + 发音清晰度 + 低置信词识别 | 8 |
| 💭 情感分析 | Comprehend 情感倾向（积极/消极/中立）| 8 |

## 架构

```
Browser (Next.js 15)              FastAPI (Python 3.12)              AWS Services
┌──────────────────┐             ┌─────────────────────┐           ┌──────────────┐
│ AudioWorklet     │  PCM16      │ /ws/interview-demo  │  bidi     │ Nova Sonic   │
│ MediaDevices     │◄───────────►│ (Strands BidiAgent) │◄─────────►│ (V2, 16kHz)  │
│ WebSocket        │  base64     │                     │           └──────────────┘
│ Tailwind UI      │  JSON       │ BidiInterviewSession│           ┌──────────────┐
│ AuthGuard        │             │ (Q/A persistence)   │  invoke   │ Claude       │
└──────────────────┘             └────────┬────────────┘◄─────────►│ (Sonnet 4.5) │
        │                                 │                        └──────────────┘
        │ HTTPS                  ┌────────┼────────┐               ┌──────────────┐
        ▼                        ▼        ▼        ▼    async      │ Transcribe   │
   CloudFront              SQLite(WAL)  S3 Audio  Seed ◄──────────►│ (zh-CN)      │
   (E1C2SHDKQ3AT2Q)                                               └──────────────┘
        │                                                          ┌──────────────┐
        ▼                                                          │ Comprehend   │
   EC2 Tokyo                                                       │ (sentiment)  │
   (Caddy :80)                                                     └──────────────┘
   ├── uvicorn :8000                                               ┌──────────────┐
   └── next :3000                                                  │ Cognito      │
                                                                   │ (JWT auth)   │
                                                                   └──────────────┘
```

## 评估维度（20 个指标）

### 内容维度 (50% 权重)
6 个 FAANG Checkpoints: STAR 结构 / 具体性 / 影响力 / 主导性 / 问题解决 / 表达清晰度

### 表达维度 (30% 权重)
5 级评分: 混乱(0-20) → 缺结构(21-40) → 清晰(41-60) → 结构化(61-80) → 突出(81-100)

### 语音维度 (20% 权重) — 扣分制 base 100

| 指标 | 来源 | 扣分规则 |
|---|---|---|
| 语速 (cps) | PCM RMS | <2.5 或 >6 字/秒 → -15 |
| 停顿频率 | PCM RMS | >15/min → -10, >25/min → -20 |
| 填充词占比 | transcript 正则 | >8% → -15, >15% → -30 |
| 说话占比 | PCM RMS | <40% → -20 |
| 首答延迟 | PCM leading silence | >3s → -5, >5s → -10, >8s → -15 |
| 犹豫次数 | PCM 200-500ms gaps | >10/min → -5, >20/min → -10 |
| 音量稳定性 | PCM RMS CV | >0.6 → -5, >1.0 → -10 |
| 发音清晰度 | Transcribe confidence | >20% 低置信 → -10 |
| 情感倾向 | Comprehend | NEGATIVE → -5 |

## 测试

| 层 | 测试数 | 命令 | 时长 |
|---|---|---|---|
| Backend | 128 pytest | `cd backend && pytest -q` | ~11s |
| Frontend | 6 vitest | `cd frontend && npm test` | ~200ms |
| Smoke | WS 脚本 | `python backend/scripts/ws_smoke.py --tone 0` | ~30s |

## 本地启动

### 前置
- Python 3.12 + [uv](https://github.com/astral-sh/uv)
- Node.js 20+ / npm
- AWS credentials (`~/.aws/credentials`) 有 `us-east-1` Bedrock + S3 + Transcribe + Comprehend 权限

### 起服

```bash
# Backend
cd backend
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Frontend (另一个终端)
cd frontend
npm install
npm run dev    # http://localhost:3000
```

浏览器打开 http://localhost:3000，点"开始面试"，允许麦克风。

### Cognito 认证（可选）

本地默认 auth disabled（`backend/.env` 不设 `COGNITO_USER_POOL_ID`）。  
启用方式：

```bash
# backend/.env
COGNITO_REGION=us-east-1
COGNITO_USER_POOL_ID=us-east-1_Yy5si2wyX
COGNITO_CLIENT_ID=54ljqt6asmevn1qchrbb0in8r1

# frontend/.env.local
NEXT_PUBLIC_COGNITO_DOMAIN=https://interviewer-mvp-484626021127.auth.us-east-1.amazoncognito.com
NEXT_PUBLIC_COGNITO_CLIENT_ID=54ljqt6asmevn1qchrbb0in8r1
```

## 生产部署

```
EC2 Tokyo (i-0c1b4bc44a1cabbf9, 52.196.0.36)
├── Caddy :80 → :8000 (api/ws) + :3000 (next)
├── systemd: interviewer-backend / interviewer-frontend / caddy
├── SG: CloudFront prefix list only (pl-58a04531) + SSH from admin IP
└── IAM: PVRE-SSMOnboardingRole + InterviewerMVP-BedrockS3 (Bedrock+S3+Transcribe+Comprehend)

CloudFront: d1hlahtkv3v1q6.cloudfront.net (E1C2SHDKQ3AT2Q)
├── HTTPS redirect-to-https
├── CachePolicy: CachingDisabled
└── Origin: EC2 :80 via prefix list

Cognito: us-east-1_Yy5si2wyX
├── Client: 54ljqt6asmevn1qchrbb0in8r1
├── Hosted UI: interviewer-mvp-484626021127.auth.us-east-1.amazoncognito.com
└── AdminCreateUserOnly (no self-signup)
```

### 部署更新

```bash
ssh -i ~/ssh/key4Tokyo.pem ubuntu@52.196.0.36
cd ~/interviewer && git pull
cd backend && ~/.local/bin/uv pip install --python .venv/bin/python -e ".[dev]"
cd ../frontend && npm run build
sudo systemctl restart interviewer-backend interviewer-frontend
```

## 项目结构

```
interviewer/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI + CORS + auth middleware
│   │   ├── auth.py                    # Cognito JWT verification
│   │   ├── routers/
│   │   │   ├── demo_bidi.py           # ❗ WS endpoint + Nova Sonic bootstrap
│   │   │   ├── interviews.py / audio.py / health.py / company_styles.py
│   │   ├── services/
│   │   │   ├── bidi_interview_session.py  # Q/A persistence + user audio accumulation
│   │   │   ├── evaluation_service.py      # Claude + Transcribe + Comprehend pipeline
│   │   │   ├── voice_analyzer.py          # 20 voice features (stdlib, no numpy)
│   │   │   ├── record_service.py / audio_service.py
│   │   ├── clients/
│   │   │   ├── bedrock_claude.py / s3_audio.py
│   │   │   ├── transcribe_client.py       # Async Transcribe job lifecycle
│   │   │   ├── comprehend_client.py       # Sentiment detection
│   │   ├── models.py                  # 5 tables: interview/question/answer/evaluation/company_style
│   │   ├── seed/                      # Company-specific seed data
│   │   └── config.py / db.py / schemas.py
│   ├── assets/hello.pcm              # ❗ Nova Sonic bootstrap greeting
│   ├── alembic/                       # DB migrations
│   ├── scripts/ws_smoke.py            # Standalone WS test client
│   └── tests/                         # 128 pytest
│
├── frontend/
│   ├── app/
│   │   ├── page.tsx                   # Interview UI (WS + AudioWorklet + PCM)
│   │   ├── history/page.tsx           # Interview list
│   │   ├── history/[id]/page.tsx      # Detail (Q/A + scores + voice metrics + audio playback)
│   │   ├── auth/callback/page.tsx     # Cognito OAuth callback
│   │   └── layout.tsx
│   ├── components/
│   │   ├── AppShell.tsx               # Nav + logout + AuthGuard wrapper
│   │   └── AuthGuard.tsx              # Redirect to Cognito if unauthenticated
│   ├── lib/
│   │   ├── auth.ts                    # Cognito Hosted UI + token refresh
│   │   ├── api.ts                     # API client with auto-refresh
│   │   └── audio-codec.ts            # base64 ↔ PCM16
│   └── public/pcm-worklet.js         # AudioWorklet for mic capture
│
├── shared/eval_core/                  # Cross-backend evaluation logic
│   ├── rubric.py                      # Scoring formulas (content + expression + voice)
│   ├── prompt_template.py             # Claude stage1/stage2 prompts
│   └── tests/                         # 46 rubric tests
│
├── deployment/
│   ├── Caddyfile / interviewer-{backend,frontend}.service
│   ├── cloudfront-config.json / s3-cors.json
│   └── README.md
│
├── aidlc-docs/                        # AIDLC workflow documentation
└── nova-sonic-poc/                    # Pre-POC probe artifacts
```

## 成本

| 服务 | 每面试 | 说明 |
|---|---|---|
| Nova Sonic | ~$0.01 | 双向流 ~2min |
| Claude Sonnet 4.5 | ~$0.12 | 5 题 stage1 + 1 stage2 |
| Transcribe | ~$0.024 | 5 answers × ~30s |
| Comprehend | ~$0.001 | 5 × sentiment |
| S3 | ~$0.001 | PCM + WAV + JSON |
| **总计** | **~$0.15** | 每次 45 分钟面试 |

## ❗ 关键技术决策

1. **Nova Sonic 永不主动开口** — 必须注入 `hello.pcm` 假装用户先说话
2. **turn_detection 必配** — V2 模型需要显式 `endpointingSensitivity: MEDIUM`
3. **Transcribe 需要 WAV 封装** — 不接受 raw PCM，需加 44 字节 WAV header
4. **EC2 :80 不能暴露公网** — Amazon Epoxy 自动隔离，必须 CloudFront prefix list + Cognito auth
5. **asyncio.create_task GC 陷阱** — 必须 module-level set 持有 Task 引用
6. **Strands API** — 锁 `strands-agents[bidi-all]>=1.37,<2.0`

## 开发工作流

**AIDLC + Agile Sprint** 混合模式。每个 Sprint 交付可体验增量，所有改动有自动化测试。

Sprint 1-2: Walking skeleton (语音流 + 持久化)  
Sprint 3: 评估 pipeline (Claude stage1/stage2)  
Sprint 4: 音频存储 + 回放  
Sprint 5: 云部署 + Cognito 认证  
Sprint 6: 语音特征分析 (PCM-based, 10 指标)  
Sprint 7: Tier 1 扩展 (volume/delay/hesitation, 14 指标)  
Sprint 8: Transcribe + Comprehend (20 指标)  

## License

Internal / WIP — 尚未公开发布。
