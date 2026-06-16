"""
Code Detective - FastAPI Backend Entry Point
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from routers import scan, graph, search, agents, mcp

app = FastAPI(
    title="Code Detective API",
    description="Repository Intelligence Engine — AST parsing, dependency graphs, vector search, and LangGraph agents.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scan.router, prefix="/api/scan", tags=["Scanner"])
app.include_router(graph.router, prefix="/api/graph", tags=["Dependency Graph"])
app.include_router(search.router, prefix="/api/search", tags=["Code Search"])
app.include_router(agents.router, prefix="/api/agents", tags=["LangGraph Agents"])
app.include_router(mcp.router, prefix="/api/mcp", tags=["MCP Layer"])


@app.get("/")
async def root():
    return {"message": "Code Detective API is running.", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
