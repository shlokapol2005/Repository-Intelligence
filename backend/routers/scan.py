"""Scan router — scan a repository, build vector index, and warm the graph cache.

Single scan pass: files are scanned once, then the same data is reused for:
  1. FAISS vector index (with AST-aware chunking)
  2. Dependency graph (pre_scanned passed directly — no second I/O pass)
  3. AST dump to disk (for verification)

index_name is an MD5 hash of the repo_path to avoid collision between repos
whose paths share the same trailing characters.
"""
import json
import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.scanner import scan_repository, read_file_content
from utils.vector_index import build_vector_index
from utils.agents import invalidate_graph, get_or_build_graph
from utils.parser import parse_file

router = APIRouter()


class ScanRequest(BaseModel):
    repo_path: str
    build_index: bool = True


@router.post("/")
async def scan_repo(req: ScanRequest):
    try:
        files = scan_repository(req.repo_path)
        if not files:
            raise HTTPException(status_code=404, detail="No supported files found in repository.")

        # ── Single scan pass ──────────────────────────────────────────────────
        # Collect (file_meta, content, parsed) once — reused for index, graph, dump.
        pre_scanned: list[tuple[dict, str, dict]] = []
        parsed_map: dict[str, dict] = {}   # relative_path → parsed AST

        for f in files:
            content = read_file_content(f["path"])
            parsed  = parse_file(f["path"], content)
            parsed["relative_path"] = f["relative_path"]
            pre_scanned.append((f, content, parsed))
            parsed_map[f["relative_path"]] = parsed

        result = {
            "repo_path": req.repo_path,
            "total_files": len(files),
            "files": files,
        }

        if req.build_index:
            # ── Stable, collision-free index name (MD5 hash of full path) ────
            index_name = hashlib.md5(req.repo_path.encode()).hexdigest()[:16]

            # ── 1. FAISS vector index with AST-aware chunking ─────────────────
            files_with_content = [
                {**f, "content": content}
                for (f, content, _) in pre_scanned
            ]
            index_result = build_vector_index(
                files_with_content,
                index_name=index_name,
                parsed_map=parsed_map,
            )

            # ── 2. Dependency graph — reuse pre_scanned, no second I/O pass ──
            invalidate_graph(req.repo_path)          # clear stale cache entry
            graph_cache = get_or_build_graph(req.repo_path, pre_scanned=pre_scanned)

            # ── 3. AST dump to disk for verification ─────────────────────────
            data_dir = Path("../data").resolve()
            data_dir.mkdir(exist_ok=True, parents=True)
            ast_file = data_dir / f"ast_parsed_{index_name}.json"
            ast_file.write_text(
                json.dumps([p for _, _, p in pre_scanned], indent=2),
                encoding="utf-8",
            )

            result["index"]          = index_result
            result["index_name"]     = index_name
            result["ast_dump_file"]  = str(ast_file)
            result["graph_stats"]    = graph_cache["dict"]["stats"]

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
