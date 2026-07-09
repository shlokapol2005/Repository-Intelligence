"""
github_app.py — GitHub App authentication.

A GitHub App can't use a static personal token. Instead it proves its identity
with a short-lived JWT signed by the app's private key, then exchanges that for a
per-installation access token (valid ~1h) scoped to whatever repos that
installation granted. Those installation tokens are what let the app clone
private repos and comment on PRs in *other people's* repositories.

Migration-friendly by design:
  - If GITHUB_APP_ID + a private key are configured AND the webhook payload
    carries an `installation.id` → App mode (installation token).
  - Otherwise → fall back to the static GITHUB_TOKEN (the original PAT flow),
    so nothing breaks before the App is registered.

Required env for App mode:
  GITHUB_APP_ID               numeric app id
  GITHUB_APP_PRIVATE_KEY      the .pem contents  (preferred on hosts like Render)
    …or GITHUB_APP_PRIVATE_KEY_PATH  path to the .pem file (local dev)
"""
from __future__ import annotations

import os
import time
import threading
from datetime import datetime, timezone

import httpx

GITHUB_API = "https://api.github.com"

# Guarded import: if PyJWT/cryptography aren't present we simply stay in PAT
# mode rather than crashing the whole backend at import time.
try:
    import jwt as _jwt  # PyJWT
    _JWT_AVAILABLE = True
except Exception:
    _JWT_AVAILABLE = False


def _private_key() -> str | None:
    """Return the app private key PEM from env (inline value or file path)."""
    key = os.getenv("GITHUB_APP_PRIVATE_KEY", "").strip()
    if key:
        # Render/dotenv often store newlines as literal "\n" — normalise them.
        return key.replace("\\n", "\n")
    path = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH", "").strip()
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None


def is_app_configured() -> bool:
    """True when GitHub App credentials are present and usable."""
    return bool(_JWT_AVAILABLE and os.getenv("GITHUB_APP_ID", "").strip() and _private_key())


def generate_app_jwt() -> str:
    """
    Create a short-lived (10 min) JWT signed with the app private key. This
    authenticates AS THE APP (not an installation) — used only to mint
    installation tokens.
    """
    app_id = os.getenv("GITHUB_APP_ID", "").strip()
    key = _private_key()
    if not (app_id and key):
        raise RuntimeError("GitHub App is not configured (missing app id or private key).")

    now = int(time.time())
    payload = {
        "iat": now - 60,     # backdate 60s to tolerate clock skew
        "exp": now + 540,    # GitHub allows max 10 min; stay safely under
        "iss": app_id,
    }
    return _jwt.encode(payload, key, algorithm="RS256")


# ── Installation token cache ─────────────────────────────────────────────────
# {installation_id: (token, expiry_epoch)} — refreshed ~1 min before expiry.
_token_cache: dict[int, tuple[str, float]] = {}
_cache_lock = threading.Lock()


def _parse_expiry(expires_at: str) -> float:
    """GitHub returns ISO-8601 like '2024-01-01T12:00:00Z'."""
    try:
        dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return time.time() + 3000  # ~50 min fallback


async def get_installation_token(installation_id: int) -> str:
    """
    Return a valid installation access token for the given installation,
    minting a fresh one via the GitHub API when the cache is empty/expired.
    """
    now = time.time()
    with _cache_lock:
        cached = _token_cache.get(installation_id)
        if cached and cached[1] - 60 > now:  # still valid (>60s left)
            return cached[0]

    app_jwt = generate_app_jwt()
    url = f"{GITHUB_API}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    token = data["token"]
    expiry = _parse_expiry(data.get("expires_at", ""))
    with _cache_lock:
        _token_cache[installation_id] = (token, expiry)
    return token


def installation_id_from_payload(payload: dict) -> int | None:
    """Extract the installation id from a GitHub App webhook payload."""
    inst = payload.get("installation") or {}
    return inst.get("id")


async def get_token(installation_id: int | None) -> str:
    """
    The single seam every webhook uses to get a GitHub token.

    App mode (configured + installation id present) → installation token.
    Otherwise                                        → static GITHUB_TOKEN (PAT).
    Returns "" if neither is available.
    """
    if is_app_configured() and installation_id:
        return await get_installation_token(installation_id)
    return os.getenv("GITHUB_TOKEN", "").strip()


async def get_token_for_event(payload: dict) -> str:
    """Convenience wrapper: resolve a token straight from a webhook payload."""
    return await get_token(installation_id_from_payload(payload))
