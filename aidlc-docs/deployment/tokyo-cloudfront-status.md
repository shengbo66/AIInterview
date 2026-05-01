# Cloud Deployment Status — Tokyo EC2 + CloudFront

> **Paused**: 2026-05-01T12:22+08:00
> **Reason**: 用户有事暂停

---

## 目标架构

```
Browser → CloudFront (*.cloudfront.net, HTTPS :443)
              ↓ /ws/*  → EC2 Tokyo :8000 (WebSocket, HTTP)
              ↓ /*     → EC2 Tokyo :3000 (Next.js, HTTP)

EC2 Tokyo (52.196.0.36, i-0c1b4bc44a1cabbf9)
  ├── uvicorn :8000 (FastAPI + WS)
  ├── next start :3000
  ├── SQLite + S3 (us-east-1, 跨区但 OK for MVP)
  └── Bedrock (us-east-1, 跨区 ~150-200ms 额外延迟)
```

## Team Review 结论

- **架构方案**: 单 EC2 (复用 Tokyo) + CloudFront HTTPS 前置
- **Review 结果**: PASS (architect + senior-dev)
- **预估工作量**: ~2 小时

## 完成的步骤

### ✅ EC2 基础信息确认
- **Instance**: `i-0c1b4bc44a1cabbf9`, Tokyo (ap-northeast-1)
- **Public IP**: 52.196.0.36
- **OS**: Ubuntu 22.04.5 LTS
- **资源**: 49 GB disk (36 GB free), 16 GB RAM
- **SSH**: `~/ssh/key4Tokyo.pem` → `ubuntu@52.196.0.36`
- **Python 现状**: 3.10.12 (需升级到 3.12)
- **Node 现状**: 未安装
- **AWS CLI**: v1 at `~/.local/bin/aws`（`AWS_PAGER=""` 前缀可用）

### ✅ IAM 权限追加 (Account 484626021127)
给 Role `PVRE-SSMOnboardingRole-17KX1K1N3IUB0` 加了 inline policy `InterviewerMVP-BedrockS3`:
- `bedrock:InvokeModel*` on `arn:aws:bedrock:us-east-1::foundation-model/*`
- `s3:PutObject/GetObject` on `arn:aws:s3:::interviewer-poc-audio-484626021127/*`
- `s3:ListBucket` on `arn:aws:s3:::interviewer-poc-audio-484626021127`

验证通过：`aws s3 ls` 和 `aws bedrock get-foundation-model` 都返回成功。

## 待完成的步骤

### ⏳ Step 1: 安装 Python 3.12 + Node 20
```bash
# Python 3.12 via deadsnakes PPA
ssh -i ~/ssh/key4Tokyo.pem ubuntu@52.196.0.36 '
  sudo add-apt-repository -y ppa:deadsnakes/ppa &&
  sudo apt-get update -qq &&
  sudo apt-get install -y -qq python3.12 python3.12-venv python3.12-dev
'

# Node 20 via NodeSource
ssh -i ~/ssh/key4Tokyo.pem ubuntu@52.196.0.36 '
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - &&
  sudo apt-get install -y nodejs
'
```

### ⏳ Step 2: 部署代码
```bash
# Clone repo（Tokyo 机器已有 SSH key 认证到 GitHub）
ssh -i ~/ssh/key4Tokyo.pem ubuntu@52.196.0.36 '
  cd ~ && git clone git@github.com:shengbo66/AIInterview.git interviewer
'

# Backend venv + deps
ssh -i ~/ssh/key4Tokyo.pem ubuntu@52.196.0.36 '
  cd ~/interviewer/backend &&
  python3.12 -m venv .venv &&
  .venv/bin/pip install -e ".[dev]" &&
  echo "/home/ubuntu/interviewer" > .venv/lib/python3.12/site-packages/interviewer-root.pth &&
  .venv/bin/alembic upgrade head
'

# Frontend build
ssh -i ~/ssh/key4Tokyo.pem ubuntu@52.196.0.36 '
  cd ~/interviewer/frontend && npm ci && npm run build
'
```

### ⏳ Step 3: 环境配置
- `backend/.env`: 需要设 AWS region + 可能的配置覆盖
- `frontend/.env.production`: `NEXT_PUBLIC_API_URL` + `NEXT_PUBLIC_WS_URL` 指向 CloudFront URL（`/ws/interview-demo` 用相对路径）
- 考虑改前端代码把 WS URL 改成相对路径（现在是硬编码 `localhost:8000`）

### ⏳ Step 4: systemd services
两个 service unit files:
- `/etc/systemd/system/interviewer-backend.service` → uvicorn
- `/etc/systemd/system/interviewer-frontend.service` → next start

### ⏳ Step 5: CloudFront Distribution
- Origin: `52.196.0.36:80`（EC2 上需要一个 HTTP 入口，或直接两个 origin: :3000 + :8000）
- 替代方案：在 EC2 上装 Caddy 做端口聚合（80 → /ws/* 到 8000, /* 到 3000）
- Cache Policy: 对 `/ws/*` 和 `/api/*` 禁用缓存
- Origin Request Policy: 转发所有 headers 和 query strings
- Origin Read Timeout: 60s（WS 长连接需要）

### ⏳ Step 6: 安全组
- EC2 SG 需要开放 :80 给 CloudFront IP range（或简化：0.0.0.0/0 然后靠 CloudFront ALB-like）
- 最终安全组：22 (SSH 你的 IP), 80 (0.0.0.0/0 给 CloudFront)

### ⏳ Step 7: 端到端验证
- `https://<cloudfront-domain>/api/health` → 200 OK
- `https://<cloudfront-domain>/` → 前端页面
- `https://<cloudfront-domain>` + 点开始面试 → WS 建立 + AI 开口

## 需要的决策（下次 resume 时问用户）

1. **部署方式**：EC2 上直接 git clone + pip install，还是要打包 tarball 上传？
   - **推荐**：git clone（Tokyo EC2 可以直连 GitHub，简单）
   - 前提：Tokyo EC2 的 SSH key 已注册到 GitHub（之前用它 scp 回来过，应该 OK）

2. **端口聚合方案**：
   - **A (推荐)**：Caddy 反向代理（:80 → /ws,/api 到 :8000; /* 到 :3000）
   - B：CloudFront 配两个 origin（复杂，WS path 匹配规则难调）

3. **CloudFront 域名**：接受 `d*.cloudfront.net` 默认域名即可，不需要 custom domain

4. **数据库迁移**：
   - 新面试直接用新 EC2 上的空 SQLite
   - 还是需要把本地的几场面试数据拷贝过去？（推荐：新数据，不拷贝）

## 风险提醒

1. **跨区延迟**：Tokyo → us-east-1 Bedrock ~150ms RTT。AI 响应会慢一些。可以 work but not optimal.
2. **SQLite 并发**：WAL 模式下 1 writer + N readers，多用户同时面试可能冲突（MVP 可接受）
3. **CloudFront WS**：需要 `Connection: Upgrade` header 转发，origin timeout 调到 60s
4. **面试中 CloudFront 缓存**：必须对 `/ws/*` 和 `/api/*` 显式禁用缓存

## Git 状态

- **Local**: 所有改动已 push 到 `git@github-ai:shengbo66/AIInterview.git`
- **Last commit**: `c824af2 fix: evaluation auto-trigger + PCM audio playback`
- **本地测试**: 57 pytest + 6 vitest = 63 测试全绿

## 下次 resume 时

Resume 方式：告诉 agent "继续部署"。应该从 **Step 1（安装 Python 3.12 + Node 20）** 开始。

预计剩余时间：1.5-2 小时（如果一切顺利）。
