"""Graph router — dependency graph, impact analysis, dead code, Mermaid."""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.agents import get_or_build_graph
from utils.graph_builder import (
    get_impact, detect_dead_code, generate_mermaid, graph_to_dict,
    build_inheritance_edges, ENTRYPOINT_NAMES,
)

router = APIRouter()

# Canonical entrypoint list lives in graph_builder so dead-code detection, the
# Mermaid diagram, and this endpoint can't disagree about what's "dead".
ENTRYPOINTS = ENTRYPOINT_NAMES


class GraphRequest(BaseModel):
    repo_path: str
    refresh: bool = False  # pull latest + rebuild (the "Rebuild Graph" button)


class ImpactRequest(BaseModel):
    repo_path: str
    target_file: str


@router.post("/build")
async def build_graph(req: GraphRequest):
    try:
        cache = get_or_build_graph(req.repo_path, refresh=req.refresh)
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


@router.post("/full")
async def full_graph(req: GraphRequest):
    """
    Return the full dependency graph in React Flow-ready format.
    Nodes carry language, AST, degree, dead-code, and entrypoint flags.
    Edges carry import names and are pre-marked as animated.
    """
    try:
        cache = get_or_build_graph(req.repo_path, refresh=req.refresh)
        G = cache["G"]

        # Pre-compute dead code (zero in-degree, non-entrypoint)
        dead_set = {
            n for n, deg in G.in_degree()
            if deg == 0 and Path(n).name not in ENTRYPOINTS
        }

        # Language breakdown for stats
        lang_counts: dict[str, int] = {}

        rf_nodes = []
        for node, data in G.nodes(data=True):
            lang = data.get("language", "unknown")
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            in_deg  = G.in_degree(node)
            out_deg = G.out_degree(node)
            is_dead = node in dead_set
            is_entry = Path(node).name in ENTRYPOINTS

            rf_nodes.append({
                "id": node,
                "type": "codeNode",
                "data": {
                    "label":       Path(node).name,
                    "path":        node,
                    "language":    lang,
                    "functions":   data.get("functions", []),
                    "classes":     data.get("classes", []),
                    "api_routes":  data.get("api_routes", []),
                    "lines":       data.get("lines", 0),
                    "size_bytes":  data.get("size_bytes", 0),
                    "in_degree":   in_deg,
                    "out_degree":  out_deg,
                    "is_dead":     is_dead,
                    "is_entrypoint": is_entry,
                },
                # Initial position — layout handled client-side
                "position": {"x": 0, "y": 0},
            })

        rf_edges = []
        for idx, (u, v, edata) in enumerate(G.edges(data=True)):
            rf_edges.append({
                "id":       f"e{idx}",
                "source":   u,
                "target":   v,
                "label":    edata.get("import_name", ""),
                "animated": True,
                "type":     "smoothstep",
            })

        # Most connected node by total degree
        most_connected = max(G.nodes(), key=lambda n: G.degree(n)) if G.nodes() else ""

        return {
            "nodes": rf_nodes,
            "edges": rf_edges,
            "inheritance": build_inheritance_edges(G),
            "stats": {
                "total_nodes":    G.number_of_nodes(),
                "total_edges":    G.number_of_edges(),
                "languages":      lang_counts,
                "dead_code_count": len(dead_set),
                "most_connected": most_connected,
                "most_connected_degree": G.degree(most_connected) if most_connected else 0,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
