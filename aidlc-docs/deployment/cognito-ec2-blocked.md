# Cognito + Deployment Status — BLOCKED

> **Blocked**: 2026-05-01T22:50+08:00
> **Reason**: Tokyo EC2 被公司合规自动化停机 + 隔离

---

## 已完成

### Cognito
- User Pool: `us-east-1_Yy5si2wyX`
- Client: `54ljqt6asmevn1qchrbb0in8r1`
- Hosted UI Domain: `interviewer-mvp-484626021127.auth.us-east-1.amazoncognito.com`
- Demo 用户: `demo@interviewer.test` / `Interview2026!`

### 代码（已 push, commit 006dfb1）
**Backend**:
- `app/auth.py`: Cognito JWT verification (python-jose + JWKS cache)
- `app/config.py`: cognito_user_pool_id / cognito_client_id env vars
- `main.py`: `AUTH = [Depends(verify_token)]` 加到 3 个 router
- `demo_bidi.py`: WS ?token= query param 验证
- Cognito 未配置时 auth 自动 disabled（本地测试仍 work）
- 57 pytest 全绿

**Frontend**:
- `lib/auth.ts`: Hosted UI redirect + token exchange + sessionStorage
- `components/AuthGuard.tsx`: 未登录自动 redirect
- `components/AppShell.tsx`: nav + 登出按钮
- `app/auth/callback/page.tsx`: OAuth code 换 token
- API + WS 自动带 token
- 6 vitest 全绿

### 部署
- Tokyo EC2 (52.196.0.36) 之前完整部署过：Caddy + systemd + CloudFront
- **CloudFront distribution**: `d1hlahtkv3v1q6.cloudfront.net`（可能还在，但 origin 挂了）

## 阻塞点

EC2 instance `i-0c1b4bc44a1cabbf9` 状态:
- **State**: stopped
- **StateReason**: "User initiated shutdown 2026-05-01 12:28:43 GMT"
- **Security Group**: 被换成 `epoxy-mitigations-isolated-ec2-vpc-656b3802`（完全无规则）

这是 Amazon **Epoxy 合规自动化**触发的"隔离"状态，不是简单的 stop/start 能解决。可能触发原因：
1. 给 PVRE-SSMOnboardingRole 加了 Bedrock + S3 inline policy（合规扫描可能不允许）
2. SG 开 :80 给 0.0.0.0/0（暴露公网）
3. 其他合规规则

## 下次选项

### A. 用个人 AWS 账号（推荐）
- 新起一个 EC2，不受公司合规自动化干扰
- 所有部署脚本复用（代码 + Caddyfile + systemd + CloudFront）
- Cognito 可以保留（跨账号引用）或重建
- 工作量: 30-60 分钟

### B. 联系 IT 申请 demo 环境
- 公司策略允许的合规 instance
- 时间不确定

### C. 放弃外部 demo，用本地 + 录屏
- 不给外部用户访问，自己录 demo
- 收反馈用其他渠道
- 零成本但受众窄

## 代码状态

所有代码已 push 到 GitHub，本地开发环境仍正常运作：
- Backend uvicorn :8000 ✅
- Frontend next :3000 ✅
- Cognito auth disabled（config 为空时自动 bypass）

本地调试 Cognito 方式（不强制）:
```bash
# backend/.env
COGNITO_USER_POOL_ID=us-east-1_Yy5si2wyX
COGNITO_CLIENT_ID=54ljqt6asmevn1qchrbb0in8r1

# frontend/.env.local
NEXT_PUBLIC_COGNITO_DOMAIN=https://interviewer-mvp-484626021127.auth.us-east-1.amazoncognito.com
NEXT_PUBLIC_COGNITO_CLIENT_ID=54ljqt6asmevn1qchrbb0in8r1
```
（但 Cognito callback URL 当前只配了 localhost:3000 和 cloudfront，本地 Cognito 登录后回调到 `http://localhost:3000/auth/callback` 应该能 work）
