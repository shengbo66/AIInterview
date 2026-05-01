"""Cognito JWT verification — minimal and self-contained.

Verifies JWT signature against Cognito's public JWKS (fetched once at startup).
Validates iss, aud/client_id, exp, token_use.

Usage:
    from fastapi import Depends
    from app.auth import verify_token

    @router.get("/me", dependencies=[Depends(verify_token)])
    async def me(claims: dict = Depends(verify_token)):
        return {"email": claims["email"]}
"""
import logging
from functools import lru_cache

import httpx
from fastapi import HTTPException, Request, status
from jose import jwt
from jose.exceptions import JWTError

from app.config import settings

logger = logging.getLogger("interviewer.auth")


@lru_cache(maxsize=1)
def _jwks() -> dict:
    """Fetch Cognito public keys once; cached for process lifetime."""
    url = (
        f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/"
        f"{settings.cognito_user_pool_id}/.well-known/jwks.json"
    )
    resp = httpx.get(url, timeout=5.0)
    resp.raise_for_status()
    logger.info("loaded JWKS from %s", url)
    return resp.json()


def verify_jwt(token: str) -> dict:
    """Verify token signature + standard claims. Returns claims dict.

    Raises HTTPException(401) on any failure.
    """
    if not settings.cognito_user_pool_id or not settings.cognito_client_id:
        # Auth disabled (local dev with no Cognito config)
        return {"email": "local-dev@example.com", "sub": "local-dev"}

    try:
        # Cognito access tokens have `client_id` claim (not `aud`).
        # ID tokens have `aud`. We accept access tokens (they're what the
        # front-end sends with API calls).
        unverified = jwt.get_unverified_claims(token)
        token_use = unverified.get("token_use")
        if token_use not in ("access", "id"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"invalid token_use: {token_use}",
            )

        # For access tokens we verify client_id manually; jwt.decode only
        # checks `aud` which access tokens don't have.
        claims = jwt.decode(
            token,
            _jwks(),
            algorithms=["RS256"],
            audience=settings.cognito_client_id if token_use == "id" else None,
            options={"verify_aud": token_use == "id"},
        )
        if token_use == "access" and claims.get("client_id") != settings.cognito_client_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="client_id mismatch",
            )
        expected_iss = (
            f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/"
            f"{settings.cognito_user_pool_id}"
        )
        if claims.get("iss") != expected_iss:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="issuer mismatch",
            )
        return claims
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"invalid token: {e}",
        ) from e


def verify_token(request: Request) -> dict:
    """FastAPI dependency: extract bearer token from Authorization header + verify."""
    if not settings.cognito_user_pool_id or not settings.cognito_client_id:
        # Auth disabled (local dev / tests)
        return {"email": "local-dev@example.com", "sub": "local-dev"}
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    token = auth.split(" ", 1)[1].strip()
    return verify_jwt(token)


def verify_ws_token(token: str | None) -> dict:
    """Verify token passed via WS query param (?token=...) — browsers can't
    set Authorization header on WebSocket connections."""
    if not settings.cognito_user_pool_id or not settings.cognito_client_id:
        # Auth disabled (local dev / tests)
        return {"email": "local-dev@example.com", "sub": "local-dev"}
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing token query param",
        )
    return verify_jwt(token)
