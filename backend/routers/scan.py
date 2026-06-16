"""Scan router — scan a repository and build vector index."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from utils.scanner import scan_repository, read_file_content
from utils.vector_index import build_vector_index
from utils.agents import invalidate_graph

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

        result = {
            "repo_path": req.repo_path,
            "total_files": len(files),
            "files": files,
        }

        if req.build_index:
            # Attach content for embedding
            files_with_content = []
            for f in files:
                content = read_file_content(f["path"])
                files_with_content.append({**f, "content": content})

            index_name = req.repo_path.replace("\\", "_").replace("/", "_").replace(":", "").strip("_")[-40:]
            index_result = build_vector_index(files_with_content, index_name=index_name)
            result["index"] = index_result
            result["index_name"] = index_name

        # Invalidate graph cache so fresh data is used
        invalidate_graph(req.repo_path)

        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
