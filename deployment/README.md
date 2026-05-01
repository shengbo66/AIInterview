# Deployment Configuration

EC2 Tokyo deployment files (stored here for reference / disaster recovery).
Actual files are installed at system paths on the EC2 instance.

## Files

- `Caddyfile` → `/etc/caddy/Caddyfile` on EC2
- `interviewer-backend.service` → `/etc/systemd/system/interviewer-backend.service`
- `interviewer-frontend.service` → `/etc/systemd/system/interviewer-frontend.service`
- `cloudfront-config.json` → used with `aws cloudfront create-distribution`

## CloudFront Distribution

- **ID**: E1C2SHDKQ3AT2Q
- **Domain**: d1hlahtkv3v1q6.cloudfront.net
- **Origin**: 52.196.0.36.nip.io:80 (Tokyo EC2 with Caddy reverse proxy)
- **Origin Request Policy**: Managed-AllViewerExceptHostHeader
- **Cache Policy**: Managed-CachingDisabled (all paths, real-time data)
- **Price Class**: PriceClass_100 (North America + Europe only, cheapest)

## EC2 Services

Started at boot via systemd:

```bash
sudo systemctl status interviewer-backend   # :8000 uvicorn
sudo systemctl status interviewer-frontend  # :3000 next start
sudo systemctl status caddy                 # :80 reverse proxy
```

## Redeployment

```bash
# SSH to Tokyo
ssh -i ~/ssh/key4Tokyo.pem ubuntu@52.196.0.36

# Pull latest code
cd ~/interviewer && git pull

# Backend (if deps changed)
cd backend && .venv/bin/pip install -e ".[dev]"
sudo systemctl restart interviewer-backend

# Frontend (if UI changed)
cd ../frontend && npm ci && npm run build
sudo systemctl restart interviewer-frontend

# Check
curl https://d1hlahtkv3v1q6.cloudfront.net/api/health
```
