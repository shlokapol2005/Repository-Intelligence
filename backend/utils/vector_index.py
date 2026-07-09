"""
FAISS Vector Index
Embeds code chunks using Gemini's text-embedding model
and stores them in a local FAISS index for semantic retrieval.

Chunking strategy (in priority order):
  1. AST-aware: chunk by function/class boundaries (when parsed AST is provided)
  2. Line-based: fixed 80-line windows with 10-line overlap (fallback)
"""
import os
import json
from pathlib import Path
from typing import Any

import faiss
import numpy as np
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

EMBEDDING_MODEL = "models/gemini-embedding-001"
INDEX_DIR = Path("../data/faiss_index")
INDEX_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = 80    # lines per chunk (line-based fallback)
CHUNK_OVERLAP = 10  # overlap lines


# ─────────────────────────────────────────────
#  Chunking helpers
# ─────────────────────────────────────────────

def _chunk_content(content: str, file_path: str) -> list[dict]:
    """Fallback: split file into fixed-size overlapping line windows."""
    lines = content.splitlines()
    chunks = []
    i = 0
    while i < len(lines):
        chunk_lines = lines[i: i + CHUNK_SIZE]
        chunks.append({
            "text": "\n".join(chunk_lines),
            "file": file_path,
            "start_line": i + 1,
            "end_line": i + len(chunk_lines),
            "chunk_type": "line-window",
        })
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _chunk_by_ast(content: str, file_path: str, parsed: dict) -> list[dict]:
    """
    Primary strategy: chunk a file by AST-level logical boundaries.
    Each chunk corresponds to one top-level function or class, including
    any preamble (imports, module docstrings) before the first symbol.

    Falls back to line-based if the AST provides fewer than 2 boundaries.
    """
    lines = content.splitlines()

    # Collect all top-level symbol start lines (0-indexed)
    boundaries: list[int] = []
    for sym in parsed.get("functions", []) + parsed.get("classes", []):
        if isinstance(sym, dict) and "line" in sym:
            lno = sym["line"] - 1   # convert to 0-indexed
            if 0 <= lno < len(lines):
                boundaries.append(lno)

    boundaries = sorted(set(boundaries))

    if len(boundaries) < 2:
        # Not enough AST info — fall back to line windows
        return _chunk_content(content, file_path)

    # Build boundary ranges: [0 → b1), [b1 → b2), ..., [bN → EOF)
    split_points = [0] + boundaries + [len(lines)]
    chunks = []
    for i in range(len(split_points) - 1):
        start = split_points[i]
        end = split_points[i + 1]
        chunk_lines = lines[start:end]
        if not chunk_lines:
            continue
        # Give the first chunk (preamble/imports) a friendly label
        chunk_type = "preamble" if i == 0 and start == 0 and boundaries[0] > 0 else "symbol"
        chunks.append({
            "text": "\n".join(chunk_lines),
            "file": file_path,
            "start_line": start + 1,
            "end_line": end,
            "chunk_type": chunk_type,
        })

    # Safety: if we somehow got 0 chunks, fall back
    return chunks if chunks else _chunk_content(content, file_path)


# ─────────────────────────────────────────────
#  Embedding
# ─────────────────────────────────────────────

def _get_embedding(text: str) -> list[float]:
    """Get embedding vector from Gemini embedding API."""
    result = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=text,
        task_type="retrieval_document",
    )
    return result["embedding"]


# ─────────────────────────────────────────────
#  Index builder
# ─────────────────────────────────────────────

def build_vector_index(
    files: list[dict],
    index_name: str = "default",
    parsed_map: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """
    Build a FAISS index from scanned repository files.

    Args:
        files:       List of dicts with 'path', 'relative_path', 'content' keys.
        index_name:  Name prefix for saved index files.
        parsed_map:  Optional dict mapping relative_path → parsed AST dict.
                     When provided, enables AST-aware chunking.

    Returns:
        {"success": True, "chunks_indexed": N, "index_path": "...", "chunking": "ast"|"line-window"}
    """
    all_chunks: list[dict] = []
    all_embeddings: list[list[float]] = []
    ast_chunks_used = 0
    line_chunks_used = 0

    # Extensions that carry meaningful code semantics for embedding.
    # Non-code files (JSON, CSS, Markdown etc.) add noise to semantic search
    # and should not be embedded — they're still scanned for the file tree.
    EMBEDDABLE_EXTENSIONS = {
        ".py", ".js", ".jsx", ".ts", ".tsx",
        ".java", ".go", ".rb", ".php",
    }

    for file_info in files:
        content = file_info.get("content", "")
        if not content.strip():
            continue

        rel_path = file_info.get("relative_path", file_info.get("path", ""))
        ext = Path(rel_path).suffix.lower()

        # Skip non-code files — they pollute semantic search
        if ext not in EMBEDDABLE_EXTENSIONS:
            continue

        # Skip files that are too large (e.g. huge JSON, OpenAPI specs)
        if len(content.encode("utf-8")) > 500_000:
            continue

        # Choose chunking strategy
        parsed = (parsed_map or {}).get(rel_path)
        if parsed and parsed.get("language") in ("python", "javascript", "typescript"):
            chunks = _chunk_by_ast(content, rel_path, parsed)
            if chunks and chunks[0].get("chunk_type") != "line-window":
                ast_chunks_used += len(chunks)
            else:
                line_chunks_used += len(chunks)
        else:
            chunks = _chunk_content(content, rel_path)
            line_chunks_used += len(chunks)

        for chunk in chunks:
            try:
                embedding = _get_embedding(chunk["text"])
                all_embeddings.append(embedding)
                all_chunks.append(chunk)
            except Exception as e:
                print(f"[VectorIndex] Embedding failed for {chunk['file']}: {e}")

    if not all_embeddings:
        return {"success": False, "error": "No embeddings generated."}

    dimension = len(all_embeddings[0])
    matrix = np.array(all_embeddings, dtype="float32")

    # Normalise for cosine similarity
    faiss.normalize_L2(matrix)
    index = faiss.IndexFlatIP(dimension)
    index.add(matrix)

    # Save index and metadata
    index_path = INDEX_DIR / f"{index_name}.faiss"
    meta_path  = INDEX_DIR / f"{index_name}_meta.json"

    faiss.write_index(index, str(index_path))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2)

    return {
        "success": True,
        "chunks_indexed": len(all_chunks),
        "ast_chunks": ast_chunks_used,
        "line_window_chunks": line_chunks_used,
        "dimension": dimension,
        "index_path": str(index_path),
        "meta_path": str(meta_path),
        "chunking": "ast+line-window" if ast_chunks_used and line_chunks_used else
                    "ast" if ast_chunks_used else "line-window",
    }


# ─────────────────────────────────────────────
#  Semantic search
# ─────────────────────────────────────────────

def semantic_search(
    query: str,
    index_name: str = "default",
    top_k: int = 8,
) -> list[dict]:
    """
    Search the FAISS index for the most relevant code chunks.

    Args:
        query:      Natural language query.
        index_name: Name of the saved index.
        top_k:      Number of results to return.

    Returns:
        List of chunk dicts with a 'score' field.
    """
    index_path = INDEX_DIR / f"{index_name}.faiss"
    meta_path  = INDEX_DIR / f"{index_name}_meta.json"

    if not index_path.exists() or not meta_path.exists():
        return []

    index = faiss.read_index(str(index_path))
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    query_embedding = _get_embedding(query)
    query_vec = np.array([query_embedding], dtype="float32")
    faiss.normalize_L2(query_vec)

    distances, indices = index.search(query_vec, top_k)

    results = []
    for score, idx in zip(distances[0], indices[0]):
        if idx < 0 or idx >= len(metadata):
            continue
        chunk = dict(metadata[idx])
        chunk["score"] = float(score)
        results.append(chunk)

    return results
