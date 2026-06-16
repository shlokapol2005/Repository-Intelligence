"""Graph router — dependency graph, impact analysis, dead code, Mermaid."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.agents import get_or_build_graph
from utils.graph_builder import get_impact, detect_dead_code, generate_mermaid, graph_to_dict

router = APIRouter()


class GraphRequest(BaseModel):
    repo_path: str


class ImpactRequest(BaseModel):
    repo_path: str
    target_file: str


@router.post("/build")
async def build_graph(req: GraphRequest):
    try:
        cache = get_or_build_graph(req.repo_path)
        return cache["dict"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mermaid")
async def get_mermaid(req: GraphRequest):
    try:
        cache = get_or_build_graph(req.repo_path)
        G = cache["G"]
        return {"mermaid": generate_mermaid(G)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/impact")
async def impact_analysis(req: ImpactRequest):
    try:
        cache = get_or_build_graph(req.repo_path)
        G = cache["G"]
        return get_impact(G, req.target_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dead-code")
async def dead_code(req: GraphRequest):
    try:
        cache = get_or_build_graph(req.repo_path)
        G = cache["G"]
        return detect_dead_code(G)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
