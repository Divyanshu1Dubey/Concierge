"""'Sign in with Google' for the clinic mailbox (OAuth 2.0, offline access).

The clinic approves access on Google's own consent screen; HeyJarvis stores only
an encrypted refresh token and uses short-lived access tokens with SMTP/IMAP
XOAUTH2. Needs GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET from a Google Cloud
OAuth client whose redirect URI is {APP_URL}/oauth/google/callback.
"""

from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt

from saas.config import get_settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
# Full mail scope is the only one Gmail accepts for SMTP/IMAP XOAUTH2.
SCOPES = "https://mail.google.com/ openid email"

_access_cache: dict[int, tuple[str, float]] = {}


class OAuthError(Exception):
    pass


def client_id() -> str | None:
    return os.environ.get("GOOGLE_CLIENT_ID")


def available() -> bool:
    return bool(client_id() and os.environ.get("GOOGLE_CLIENT_SECRET"))


def redirect_uri() -> str:
    return get_settings().app_url.rstrip("/") + "/oauth/google/callback"


def start_url(tenant_id: int, user_id: int, login_hint: str | None = None, from_name: str | None = None) -> str:
    if not available():
        raise OAuthError("Google sign-in is not configured on this server (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).")
    state = jwt.encode({"tid": tenant_id, "uid": user_id, "n": secrets.token_urlsafe(8), "purpose": "google_mailbox", "fn": (from_name or "")[:120],
                        "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
                       get_settings().jwt_secret, algorithm="HS256")
    params = {"client_id": client_id(), "redirect_uri": redirect_uri(), "response_type": "code", "scope": SCOPES,
              "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true", "state": state}
    if login_hint:
        params["login_hint"] = login_hint
    return AUTH_URL + "?" + urlencode(params)


def read_state(state: str) -> dict:
    try:
        claims = jwt.decode(state, get_settings().jwt_secret, algorithms=["HS256"])
    except JWTError as e:
        raise OAuthError("This sign-in link expired or was tampered with. Start again from Settings.") from e
    if claims.get("purpose") != "google_mailbox":
        raise OAuthError("invalid state")
    return claims


def exchange_code(code: str) -> dict:
    """Returns {'email', 'refresh_token', 'access_token', 'expires_in'}."""
    r = httpx.post(TOKEN_URL, data={"code": code, "client_id": client_id(),
                                    "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                                    "redirect_uri": redirect_uri(), "grant_type": "authorization_code"}, timeout=20)
    if r.status_code != 200:
        raise OAuthError(f"Google rejected the sign-in: {r.text[:200]}")
    tok = r.json()
    if "https://mail.google.com/" not in tok.get("scope", ""):
        raise OAuthError("Mail access was not granted. Tick the Gmail permission on Google's screen and try again.")
    if not tok.get("refresh_token"):
        raise OAuthError("Google did not return a long-lived token. Remove HeyJarvis under Google Account → Security → "
                         "Third-party access, then connect again.")
    info = httpx.get(USERINFO_URL, headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=20)
    email = (info.json() if info.status_code == 200 else {}).get("email")
    if not email:
        raise OAuthError("Could not read the Google account's email address.")
    return {"email": email.lower(), "refresh_token": tok["refresh_token"], "access_token": tok["access_token"],
            "expires_in": int(tok.get("expires_in", 3600))}


def access_token(tenant_id: int, refresh_token: str) -> str:
    cached = _access_cache.get(tenant_id)
    if cached and cached[1] > time.time() + 60:
        return cached[0]
    r = httpx.post(TOKEN_URL, data={"client_id": client_id(), "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
                                    "refresh_token": refresh_token, "grant_type": "refresh_token"}, timeout=20)
    if r.status_code != 200:
        _access_cache.pop(tenant_id, None)
        raise OAuthError("Google access was revoked or expired. Reconnect the mailbox in Settings.")
    tok = r.json()
    _access_cache[tenant_id] = (tok["access_token"], time.time() + int(tok.get("expires_in", 3600)))
    return tok["access_token"]


def remember(tenant_id: int, token: str, expires_in: int) -> None:
    _access_cache[tenant_id] = (token, time.time() + expires_in)


def forget(tenant_id: int, refresh_token: str | None) -> None:
    _access_cache.pop(tenant_id, None)
    if refresh_token:
        try:
            httpx.post(REVOKE_URL, data={"token": refresh_token}, timeout=10)
        except Exception:
            pass


def xoauth2(user: str, token: str) -> str:
    return f"user={user}\x01auth=Bearer {token}\x01\x01"
