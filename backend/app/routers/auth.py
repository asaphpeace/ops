import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from jose import jwt

from app.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
ALLOWED_DOMAIN = "sedna.com"

# In-memory state store: {state_token: expires_at}
# Safe because uvicorn runs with --workers 1 (enforced in docker-compose.yml)
_pending_states: dict[str, float] = {}


@router.get("/google")
async def google_login():
    if not settings.auth_enabled:
        raise HTTPException(503, "Google OAuth not configured")

    state = secrets.token_urlsafe(32)
    _pending_states[state] = time.time() + 600  # 10-minute window

    # Prune expired states to prevent unbounded growth
    now = time.time()
    expired = [k for k, exp in _pending_states.items() if exp < now]
    for k in expired:
        _pending_states.pop(k, None)

    params = urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    })
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{params}")


@router.get("/google/callback")
async def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
    if error:
        return RedirectResponse("/login?error=access_denied")

    expires_at = _pending_states.pop(state, None)
    if expires_at is None or expires_at < time.time():
        return RedirectResponse("/login?error=invalid_state")

    async with httpx.AsyncClient() as client:
        token_res = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        })
        if token_res.status_code != 200:
            return RedirectResponse("/login?error=token_exchange_failed")

        tokens = token_res.json()
        user_res = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if user_res.status_code != 200:
            return RedirectResponse("/login?error=userinfo_failed")
        user = user_res.json()

    email: str = user.get("email", "")
    if not user.get("email_verified") or not email.lower().endswith(f"@{ALLOWED_DOMAIN}"):
        return RedirectResponse(f"/login?error=domain_not_allowed&email={email}")

    payload = {
        "sub": email,
        "name": user.get("name", email),
        "picture": user.get("picture", ""),
        "exp": datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)

    # Redirect to frontend root; JS picks up the token and removes it from the URL
    return RedirectResponse(f"/?token={token}")


@router.get("/me")
async def me(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(auth[7:], settings.secret_key, algorithms=[settings.algorithm])
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    return {
        "email": payload["sub"],
        "name": payload.get("name"),
        "picture": payload.get("picture"),
    }
