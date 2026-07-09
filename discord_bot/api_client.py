"""
api_client.py — Async HTTP client that calls the Code Detective FastAPI backend.

All functions are async (using httpx.AsyncClient) so they never block
the Discord bot's event loop.
"""
import os
import httpx

BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")
if "$PORT" in BASE_URL:
    BASE_URL = BASE_URL.replace("$PORT", os.getenv("PORT", "8000"))

# Generous timeout: LLM agent calls can take 15–60 seconds for large repos
_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


async def clone_repo(github_url: str) -> dict:
    """Clone a GitHub repo via POST /api/mcp/github/clone"""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/api/mcp/github/clone",
            json={"github_url": github_url},
        )
        resp.raise_for_status()
        return resp.json()


async def scan_repo(repo_path: str) -> dict:
    """Scan a repo and build vector index via POST /api/scan/"""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/api/scan/",
            json={"repo_path": repo_path, "build_index": True},
        )
        resp.raise_for_status()
        return resp.json()


async def ask_question(repo_path: str, index_name: str, question: str) -> dict:
    """Q&A agent via POST /api/agents/qa"""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/api/agents/qa",
            json={
                "question": question,
                "repo_path": repo_path,
                "index_name": index_name,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def trace_flow(repo_path: str, index_name: str, feature: str) -> dict:
    """Feature flow tracer via POST /api/agents/flow"""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/api/agents/flow",
            json={
                "feature": feature,
                "repo_path": repo_path,
                "index_name": index_name,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_impact(repo_path: str, target_file: str) -> dict:
    """Impact analysis via POST /api/agents/impact"""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/api/agents/impact",
            json={
                "target_file": target_file,
                "repo_path": repo_path,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_architecture(repo_path: str) -> dict:
    """Architecture diagram via POST /api/agents/architecture"""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/api/agents/architecture",
            json={"repo_path": repo_path},
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            try:
                detail = e.response.json().get("detail", str(e))
            except Exception:
                detail = e.response.text or str(e)
            raise Exception(detail)
        return resp.json()


async def render_mermaid_png(mermaid: str) -> bytes | None:
    """
    Render Mermaid source to PNG bytes via POST /api/render/mermaid.
    Returns None on failure so the caller can fall back to a text diagram.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{BASE_URL}/api/render/mermaid",
                json={"mermaid": mermaid},
            )
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:
        pass
    return None


async def get_dead_code(repo_path: str) -> dict:
    """Dead code detection via POST /api/graph/dead-code"""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/api/graph/dead-code",
            json={"repo_path": repo_path},
        )
        resp.raise_for_status()
        return resp.json()


async def get_onboarding(repo_path: str) -> dict:
    """Onboarding guide via POST /api/agents/onboard"""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{BASE_URL}/api/agents/onboard",
            json={"repo_path": repo_path},
        )
        resp.raise_for_status()
        return resp.json()
