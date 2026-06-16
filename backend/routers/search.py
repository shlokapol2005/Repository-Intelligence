"""Search router — semantic and code search."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.vector_index import semantic_search
from utils.mcp_layer import code_search_mcp

router = APIRouter()


class SemanticSearchRequest(BaseModel):
    query: str
    index_name: str
    top_k: int = 8


class CodeSearchRequest(BaseModel):
    query: str
    repo_path: str
    extensions: list[str] | None = None
    case_sensitive: bool = False
    max_results: int = 50


@router.post("/semantic")
async def semantic(req: SemanticSearchRequest):
    try:
        results = semantic_search(req.query, req.index_name, req.top_k)
        return {"results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/code")
async def code_search(req: CodeSearchRequest):
    try:
        result = code_search_mcp(
            query=req.query,
            repo_root=req.repo_path,
            extensions=req.extensions,
            case_sensitive=req.case_sensitive,
            max_results=req.max_results,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
