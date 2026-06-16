"""MCP router — GitHub clone, filesystem reads, code search, terminal."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.mcp_layer import (
    github_mcp_clone,
    filesystem_mcp_read,
    filesystem_mcp_list,
    code_search_mcp,
    terminal_mcp_run,
)

router = APIRouter()


class CloneRequest(BaseModel):
    github_url: str


class FileReadRequest(BaseModel):
    file_path: str
    repo_root: str


class FilesListRequest(BaseModel):
    directory: str
    repo_root: str


class CodeSearchRequest(BaseModel):
    query: str
    repo_path: str
    extensions: list[str] | None = None
    case_sensitive: bool = False
    max_results: int = 50


class TerminalRequest(BaseModel):
    command: str
    cwd: str


@router.post("/github/clone")
async def clone_repo(req: CloneRequest):
    result = github_mcp_clone(req.github_url)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/fs/read")
async def read_file(req: FileReadRequest):
    result = filesystem_mcp_read(req.file_path, req.repo_root)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.post("/fs/list")
async def list_files(req: FilesListRequest):
    result = filesystem_mcp_list(req.directory, req.repo_root)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.post("/search")
async def code_search(req: CodeSearchRequest):
    result = code_search_mcp(
        query=req.query,
        repo_root=req.repo_path,
        extensions=req.extensions,
        case_sensitive=req.case_sensitive,
        max_results=req.max_results,
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/terminal")
async def run_terminal(req: TerminalRequest):
    result = terminal_mcp_run(req.command, req.cwd)
    if not result.get("success"):
        raise HTTPException(status_code=403, detail=result.get("error"))
    return result
