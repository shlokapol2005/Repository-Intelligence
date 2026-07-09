"""
diagram_renderer.py — Render Mermaid diagram source to a PNG image.

Rendering Mermaid normally needs a headless browser (mermaid-cli + Chromium),
which is heavy and awkward on a free-tier Python host. Instead we POST the
diagram text to a Kroki server (https://kroki.io by default, self-hostable via
the KROKI_URL env var) and get back a PNG — no Node/Chromium dependency here.

Kept surface-agnostic on purpose: the Discord bot, a future Slack adapter, and
the web backend all render through this one function.
"""
from __future__ import annotations

import os

import httpx

# Public Kroki instance by default; point KROKI_URL at a self-hosted instance
# for privacy (the diagram source is sent to whichever instance is configured).
KROKI_URL = os.getenv("KROKI_URL", "https://kroki.io").rstrip("/")

_RENDER_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


async def render_mermaid_png(mermaid: str) -> bytes | None:
    """
    Render Mermaid source to PNG bytes. Returns None on any failure so callers
    can gracefully fall back to posting the raw diagram + a link instead of
    erroring out the whole command.
    """
    if not mermaid or not mermaid.strip():
        return None

    url = f"{KROKI_URL}/mermaid/png"
    try:
        async with httpx.AsyncClient(timeout=_RENDER_TIMEOUT) as client:
            resp = await client.post(
                url,
                content=mermaid.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
            )
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:
        pass
    return None


def render_mermaid_png_sync(mermaid: str) -> bytes | None:
    """Blocking variant for non-async callers (e.g. the web backend endpoint)."""
    if not mermaid or not mermaid.strip():
        return None
    url = f"{KROKI_URL}/mermaid/png"
    try:
        resp = httpx.post(
            url,
            content=mermaid.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
            timeout=_RENDER_TIMEOUT,
        )
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:
        pass
    return None
