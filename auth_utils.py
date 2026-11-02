"""Shared Google sign-in verification + app-session JWT helpers.

Mirrors the pattern used in genai-resource-management-tool-backend
(core/views.py + core/authentication.py): the client sends a Google-issued
ID token to a login endpoint, which verifies it against Google's certs with
`google-auth`, checks the email against an explicit allowlist, and mints the
app's own signed JWT. That app JWT (not the Google token) is what gets sent
as `Authorization: Bearer <token>` on every subsequent request, and is
verified here via `require_auth`.

Only three accounts are allowed in for now: pinal, raxit, and marmik
(@raapidinc.com).
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
from fastapi import Header, HTTPException
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

ROOT = Path(__file__).resolve().parent

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")

ALLOWED_EMAILS = {
    "pinal@raapidinc.com",
    "raxit@raapidinc.com",
    "marmik@raapidinc.com",
}

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 480


# The JWT signing secret deliberately lives OUTSIDE prompts.db: prompts.db is
# tracked in git (it's the source of truth for prompts/schemas), and a
# session-signing secret must never end up in commit history. An env var wins
# if set (e.g. for shared/prod deployments); otherwise it's generated once
# and cached in a gitignored local file.
_SECRET_FILE = ROOT / ".jwt_secret"


def _get_or_create_jwt_secret() -> str:
    env_secret = os.getenv("JWT_SECRET", "").strip()
    if env_secret:
        return env_secret

    if _SECRET_FILE.exists():
        existing = _SECRET_FILE.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    secret = secrets.token_hex(32)
    _SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret


JWT_SECRET = _get_or_create_jwt_secret()


def verify_google_id_token(token: str) -> dict:
    """Verifies a Google-issued ID token and enforces the email allowlist.

    Returns the decoded token claims (email, name, picture, ...) on success.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID is not configured on the server.",
        )
    try:
        idinfo = id_token.verify_oauth2_token(
            token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Google ID token: {exc}") from exc

    email = (idinfo.get("email") or "").lower()
    if email not in ALLOWED_EMAILS:
        raise HTTPException(
            status_code=403,
            detail="This account is not authorized to access this app.",
        )
    return idinfo


def mint_app_jwt(email: str, name: str = "", picture: str = "") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "name": name,
        "picture": picture,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_app_jwt(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid session token.") from exc


def require_auth(authorization: Optional[str] = Header(default=None)) -> dict:
    """FastAPI dependency: verifies the app JWT on `Authorization: Bearer <token>`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in required.")
    token = authorization.split(" ", 1)[1].strip()
    payload = _decode_app_jwt(token)
    if str(payload.get("sub", "")).lower() not in ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="This account is not authorized to access this app.")
    return payload
