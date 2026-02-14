"""Google Antigravity OAuth flow — exact replica of the TS extension.

Uses PKCE (S256), a fixed localhost callback on port 51121, and the
same client credentials / scopes as the openclaw extension.

Flow:
1. Generate PKCE verifier + challenge.
2. Start a local HTTP server on ``localhost:51121/oauth-callback``.
3. Open the user's browser to the Google OAuth consent URL.
4. Google redirects back with an auth code.
5. Exchange the code (+ verifier) for access + refresh tokens.
6. Fetch user email and Cloud Code Assist project ID.
7. Store everything in the PyClaw config.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import webbrowser
from typing import Any, Optional
from urllib.parse import urlencode

import aiohttp
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from pyclaw.config.config import Config

# ── OAuth constants (same as TS extension) ──────────────────────────
_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"
_CLIENT_SECRET = "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"
_REDIRECT_URI = "http://localhost:51121/oauth-callback"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DEFAULT_PROJECT_ID = "rising-fact-p41fc"

_SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/cclog",
    "https://www.googleapis.com/auth/experimentsandconfigs",
]

_CODE_ASSIST_ENDPOINTS = [
    "https://cloudcode-pa.googleapis.com",
    "https://daily-cloudcode-pa.sandbox.googleapis.com",
]

_RESPONSE_PAGE = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>PyClaw Antigravity OAuth</title>
    <style>
      body {
        font-family: system-ui, -apple-system, sans-serif;
        display: flex; justify-content: center; align-items: center;
        height: 100vh; margin: 0;
        background: #0d1117; color: #e6edf3;
      }
      .wrap { text-align: center; }
      h1 { font-size: 3rem; margin-bottom: 0.5rem; }
      p { color: #8b949e; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <h1>🦞</h1>
      <h2>Authentication complete</h2>
      <p>You can close this tab and return to the terminal.</p>
    </div>
  </body>
</html>"""


# ── PKCE ────────────────────────────────────────────────────────────


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE verifier and S256 challenge."""
    verifier = secrets.token_hex(32)  # 64-char hex string (same as TS)
    challenge = hashlib.sha256(verifier.encode()).digest()
    # base64url encode without padding
    import base64

    challenge_b64 = base64.urlsafe_b64encode(challenge).rstrip(b"=").decode()
    return verifier, challenge_b64


# ── Result container ────────────────────────────────────────────────
_auth_result: dict[str, Any] = {}
_auth_event: asyncio.Event = asyncio.Event()


def _build_app(state_token: str) -> FastAPI:
    """Build the FastAPI app that handles the OAuth callback."""
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/oauth-callback", response_class=HTMLResponse)
    async def oauth_callback(request: Request) -> HTMLResponse:
        global _auth_result

        received_state = request.query_params.get("state", "")
        if received_state != state_token:
            _auth_result = {"error": "OAuth state mismatch. Please try again."}
            _auth_event.set()
            return HTMLResponse(
                "<h1>⚠️ State mismatch — request rejected.</h1>", status_code=400
            )

        code = request.query_params.get("code")
        error = request.query_params.get("error")

        if error:
            _auth_result = {"error": error}
            _auth_event.set()
            return HTMLResponse(f"<h1>❌ Auth failed: {error}</h1>", status_code=400)

        if not code:
            _auth_result = {"error": "no_code"}
            _auth_event.set()
            return HTMLResponse("<h1>❌ No auth code received.</h1>", status_code=400)

        _auth_result = {"code": code, "state": received_state}
        _auth_event.set()

        return HTMLResponse(_RESPONSE_PAGE, status_code=200)

    return app


def _build_auth_url(challenge: str, state: str) -> str:
    """Build the Google OAuth consent URL (matches TS buildAuthUrl)."""
    params = {
        "client_id": _CLIENT_ID,
        "response_type": "code",
        "redirect_uri": _REDIRECT_URI,
        "scope": " ".join(_SCOPES),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


async def _exchange_code(code: str, verifier: str) -> dict[str, Any]:
    """Exchange the auth code + PKCE verifier for tokens."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            _TOKEN_URL,
            data={
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": _REDIRECT_URI,
                "code_verifier": verifier,
            },
        ) as resp:
            data = await resp.json()

    if not resp.ok or "error" in data:
        raise RuntimeError(
            f"Token exchange failed: {data.get('error_description', data.get('error', 'unknown'))}"
        )

    access = (data.get("access_token") or "").strip()
    refresh = (data.get("refresh_token") or "").strip()
    expires_in = data.get("expires_in", 0)

    if not access:
        raise RuntimeError("Token exchange returned no access_token")
    if not refresh:
        raise RuntimeError("Token exchange returned no refresh_token")

    import time

    expires = time.time() + expires_in - 5 * 60  # 5-min safety margin (same as TS)
    return {"access": access, "refresh": refresh, "expires": expires}


async def _fetch_user_email(access_token: str) -> Optional[str]:
    """Fetch the user's email from Google userinfo."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://www.googleapis.com/oauth2/v1/userinfo?alt=json",
                headers={"Authorization": f"Bearer {access_token}"},
            ) as resp:
                if not resp.ok:
                    return None
                data = await resp.json()
                return data.get("email")
    except Exception:
        return None


async def _fetch_project_id(access_token: str) -> str:
    """Fetch the Cloud Code Assist project ID (same as TS fetchProjectId)."""
    import json as json_mod

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "google-api-nodejs-client/9.15.1",
        "X-Goog-Api-Client": "google-cloud-sdk vscode_cloudshelleditor/0.1",
        "Client-Metadata": json_mod.dumps(
            {
                "ideType": "IDE_UNSPECIFIED",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI",
            }
        ),
    }

    body = json_mod.dumps(
        {
            "metadata": {
                "ideType": "IDE_UNSPECIFIED",
                "platform": "PLATFORM_UNSPECIFIED",
                "pluginType": "GEMINI",
            }
        }
    )

    for endpoint in _CODE_ASSIST_ENDPOINTS:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{endpoint}/v1internal:loadCodeAssist",
                    headers=headers,
                    data=body,
                ) as resp:
                    if not resp.ok:
                        continue
                    data = await resp.json()
                    proj = data.get("cloudaicompanionProject")
                    if isinstance(proj, str):
                        return proj
                    if isinstance(proj, dict) and proj.get("id"):
                        return proj["id"]
        except Exception:
            continue

    return _DEFAULT_PROJECT_ID


# ── Public API ──────────────────────────────────────────────────────


async def start_auth_flow() -> dict[str, Any]:
    """Run the full OAuth flow. Returns token dict or error dict.

    This starts a FastAPI server on port 51121, opens the browser,
    waits for the callback, exchanges tokens, fetches email+project,
    and shuts down the server.
    """
    global _auth_result, _auth_event
    _auth_result = {}
    _auth_event = asyncio.Event()

    verifier, challenge = _generate_pkce()
    state = secrets.token_hex(16)

    app = _build_app(state)

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=51121,
        log_level="error",
    )
    server = uvicorn.Server(config)

    # Run server in background
    server_task = asyncio.create_task(server.serve())

    # Build consent URL
    auth_url = _build_auth_url(challenge, state)

    # Open browser
    webbrowser.open(auth_url)

    # Wait for callback (timeout 5 minutes, same as TS)
    try:
        await asyncio.wait_for(_auth_event.wait(), timeout=300)
    except asyncio.TimeoutError:
        _auth_result = {"error": "Timed out waiting for OAuth callback"}

    # Shutdown server
    server.should_exit = True
    await server_task

    if "error" in _auth_result:
        return _auth_result

    code = _auth_result.get("code", "")
    if not code:
        return {"error": "Missing OAuth code"}

    # Exchange code for tokens
    try:
        tokens = await _exchange_code(code, verifier)
    except RuntimeError as exc:
        return {"error": str(exc)}

    # Fetch email and project ID
    email = await _fetch_user_email(tokens["access"])
    project_id = await _fetch_project_id(tokens["access"])

    return {
        "access_token": tokens["access"],
        "refresh_token": tokens["refresh"],
        "expires": tokens["expires"],
        "email": email,
        "project_id": project_id,
    }


async def refresh_token_if_needed(cfg: Config) -> Optional[str]:
    """Refresh the access token if expired. Returns current access token."""
    import time

    token = cfg.get("auth.google_token")
    refresh = cfg.get("auth.google_refresh_token")
    expiry = cfg.get("auth.token_expiry")

    if not token and not refresh:
        return None

    # Check if token is still valid
    if expiry and time.time() < float(expiry):
        return token

    if not refresh:
        return token  # Can't refresh, return what we have

    # Refresh the token
    async with aiohttp.ClientSession() as session:
        async with session.post(
            _TOKEN_URL,
            data={
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
                "refresh_token": refresh,
                "grant_type": "refresh_token",
            },
        ) as resp:
            data = await resp.json()

    if "error" in data:
        return None

    new_token = data.get("access_token")
    expires_in = data.get("expires_in", 3600)

    cfg.set("auth.google_token", new_token)
    cfg.set("auth.token_expiry", str(time.time() + expires_in - 300))
    await cfg.save()

    return new_token
