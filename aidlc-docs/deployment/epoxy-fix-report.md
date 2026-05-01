# Epoxy Mitigation — Fix Report

**Ticket trigger**: DyePack.EC2IPAuthentication
**Endpoint**: http://52.196.0.36:80
**ENI**: eni-016dc86bd24ebba3e
**Instance**: i-0c1b4bc44a1cabbf9 (Tokyo, ap-northeast-1)
**Account**: 484626021127 (isengard_personal=True, isengard_status=ACTIVE)

## Root Cause

The EC2 instance hosted an HTTP endpoint (Caddy reverse proxy on :80 forwarding
to FastAPI backend :8000 and Next.js frontend :3000) without any authentication.
The security group allowed `0.0.0.0/0` ingress on port 80, making an
unauthenticated endpoint publicly reachable by IP.

This is an MVP interview simulator (`github.com/shengbo66/AIInterview`) intended
to collect demo feedback. Authentication was planned but not fully integrated at
the moment of exposure.

## Remediation Applied

### 1. Application-layer authentication (Cognito JWT)

All non-health API routes and the WebSocket endpoint now require a valid
Cognito-issued JWT.

**Commit**: `006dfb1` (pushed to GitHub, branch `main`)

Backend changes:
- `backend/app/auth.py`: JWT verifier using `python-jose` + Cognito JWKS (cached)
  - Validates `iss` = `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_Yy5si2wyX`
  - Validates `client_id` = `54ljqt6asmevn1qchrbb0in8r1`
  - Validates `token_use` ∈ `{access, id}`
  - Validates signature via RS256 against Cognito's public JWKS
- `backend/app/main.py`: `Depends(verify_token)` applied to:
  - `/api/company-styles/*`
  - `/api/interviews/*`
  - `/api/interviews/{id}/audio/*`
  - `/api/interviews/{id}/questions/{qid}/audio`
- `backend/app/routers/demo_bidi.py`: WebSocket `/ws/interview-demo` verifies
  JWT from `?token=...` query parameter before `websocket.accept()`
- Only `/api/health` remains public (for load-balancer / monitoring healthchecks)

Frontend changes:
- `frontend/lib/auth.ts`: Cognito Hosted UI redirect flow (OAuth2 code grant)
- `frontend/components/AuthGuard.tsx`: unauthenticated page visits are
  redirected to `https://interviewer-mvp-484626021127.auth.us-east-1.amazoncognito.com/login`
- `frontend/app/auth/callback/page.tsx`: exchanges auth code for tokens
- API calls automatically include `Authorization: Bearer <access_token>`
- WebSocket URL appends `?token=<access_token>`

### 2. Cognito User Pool configured

- **User Pool**: `us-east-1_Yy5si2wyX` (arn: `arn:aws:cognito-idp:us-east-1:484626021127:userpool/us-east-1_Yy5si2wyX`)
- **Client**: `54ljqt6asmevn1qchrbb0in8r1`
- **Hosted UI**: `interviewer-mvp-484626021127.auth.us-east-1.amazoncognito.com`
- `AdminCreateUserOnly=true` (no self-signup)
- Password policy: min 8 chars, upper + lower + digit required
- Allowed callback URLs restricted to `https://d1hlahtkv3v1q6.cloudfront.net/auth/callback`
  and `http://localhost:3000/auth/callback`

### 3. Security group — planned restriction to CloudFront

After the isolated SG is rolled back, ingress on :80 will be limited to the
AWS Managed Prefix List for CloudFront origin-facing IPs:

```
IpPermissions:
  - FromPort: 80
    ToPort:   80
    IpProtocol: tcp
    PrefixListIds:
      - PrefixListId: pl-82a045eb   # com.amazonaws.global.cloudfront.origin-facing (us-east-1)
```

Port 80 will no longer accept traffic from arbitrary `0.0.0.0/0`. Only
CloudFront edge servers can reach the origin, and CloudFront itself is
HTTPS-only (`ViewerProtocolPolicy: redirect-to-https`). End users connect
to `https://d1hlahtkv3v1q6.cloudfront.net` and are gated by Cognito login
before any backend endpoint responds.

### 4. Tests

- 57 pytest (backend) covers auth disabled + JWT validation paths — all green
- 6 vitest (frontend) — all green

## Verification Steps (post-rollback)

1. Start services on EC2:
   ```
   sudo systemctl restart interviewer-backend interviewer-frontend caddy
   ```
2. Verify unauth rejection:
   ```
   $ curl -s -o /dev/null -w "%{http_code}\n" http://52.196.0.36/api/interviews
   401
   ```
3. Verify WebSocket unauth rejection:
   ```
   $ wscat -c ws://52.196.0.36/ws/interview-demo
   error: Unexpected server response: 401
   ```
4. Verify CloudFront works end-to-end with valid Cognito token:
   - Visit `https://d1hlahtkv3v1q6.cloudfront.net` → redirected to Cognito
   - Login as `demo@interviewer.test`
   - Redirected back, `/api/interviews` returns 200

## Rollback Request

Per Epoxy process, requesting rollback of isolated security group
`sg-061cee381e3e94dc3 (epoxy-mitigations-isolated-ec2-vpc-656b3802)` back
to original `tv-agent-sg` on ENI `eni-016dc86bd24ebba3e`.

**Will NOT reopen :80 to 0.0.0.0/0**. After rollback, will immediately
add the CloudFront prefix list restriction described in section 3.

## References

- Repo: https://github.com/shengbo66/AIInterview
- Key commit: https://github.com/shengbo66/AIInterview/commit/006dfb1
- CloudFront: `d1hlahtkv3v1q6.cloudfront.net` (E1C2SHDKQ3AT2Q)
- Cognito: `us-east-1_Yy5si2wyX` / `54ljqt6asmevn1qchrbb0in8r1`
