"""
Code Detective - FastAPI Backend Entry Point
"""
import sys
import types

# ── Compatibility patch ────────────────────────────────────────────────────────
# langgraph 0.2.x internally accesses `langchain.debug`, but the top-level
# `langchain` package may not be installed (only langchain-core is required).
# Inject a minimal stub so the attribute lookup never raises AttributeError.
if "langchain" not in sys.modules:
    _lc_stub = types.ModuleType("langchain")
    _lc_stub.debug = False
    sys.modules["langchain"] = _lc_stub
else:
    import langchain as _lc_pkg
    if not hasattr(_lc_pkg, "debug"):
        _lc_pkg.debug = False
# ──────────────────────────────────────────────────────────────────────────────

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from routers import scan, graph, search, agents, mcp, webhook, render

app = FastAPI(
    title="Code Detective API",
    description="Repository Intelligence Engine — AST parsing, dependency graphs, vector search, AI agents & pipelines.",
    version="1.0.0",
)

# Default origins cover local dev (Vite) and the deployed frontend; override/extend
# via CORS_ORIGINS (comma-separated) without touching code for other deployments.
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "https://repo-lens-gold.vercel.app",
]
_env_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_env_origins or _default_origins,
    allow_credentials=False,  # no cookies/session auth is used anywhere in this app
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scan.router, prefix="/api/scan", tags=["Scanner"])
app.include_router(graph.router, prefix="/api/graph", tags=["Dependency Graph"])
app.include_router(search.router, prefix="/api/search", tags=["Code Search"])
app.include_router(agents.router, prefix="/api/agents", tags=["AI Features"])
app.include_router(mcp.router, prefix="/api/mcp", tags=["MCP Layer"])
app.include_router(render.router, prefix="/api/render", tags=["Diagram Rendering"])
app.include_router(webhook.router, prefix="/webhook", tags=["GitHub Webhook"])


@app.get("/")
async def root():
    return {"message": "Code Detective API is running.", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
