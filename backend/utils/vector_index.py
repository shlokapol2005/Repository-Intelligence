"""
FAISS Vector Index
Embeds code chunks using Gemini's text-embedding model
and stores them in a local FAISS index for semantic retrieval.
"""
import os
import json
import hashlib
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

CHUNK_SIZE = 80   # lines per chunk
CHUNK_OVERLAP = 10  # overlap lines


def _chunk_content(content: str, file_path: str) -> list[dict]:
    """Split a file's content into overlapping chunks."""
    lines = content.splitlines()
    chunks = []
    i = 0
    while i < len(lines):
        chunk_lines = lines[i: i + CHUNK_SIZE]
        chunk_text = "\n".join(chunk_lines)
        chunks.append({
            "text": chunk_text,
            "file": file_path,
            "start_line": i + 1,
            "end_line": i + len(chunk_lines),
        })
        i += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _get_embedding(text: str) -> list[float]:
    """Get embedding vector from Gemini embedding API."""
    result = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=text,
        task_type="retrieval_document",
    )
    return result["embedding"]


def build_vector_index(
    files: list[dict],
    index_name: str = "default",
) -> dict[str, Any]:
    """
    Build a FAISS index from scanned repository files.

    Args:
        files: List of dicts with 'path', 'relative_path', 'content' keys.
        index_name: Name prefix for saved index files.

    Returns:
        {"success": True, "chunks_indexed": N, "index_path": "..."}
    """
    all_chunks = []
    all_embeddings = []

    for file_info in files:
        content = file_info.get("content", "")
        if not content.strip():
            continue

        chunks = _chunk_content(content, file_info["relative_path"])
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
    meta_path = INDEX_DIR / f"{index_name}_meta.json"

    faiss.write_index(index, str(index_path))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, indent=2)

    return {
        "success": True,
        "chunks_indexed": len(all_chunks),
        "dimension": dimension,
        "index_path": str(index_path),
        "meta_path": str(meta_path),
    }


def semantic_search(
    query: str,
    index_name: str = "default",
    top_k: int = 8,
) -> list[dict]:
    """
    Search the FAISS index for the most relevant code chunks.

    Args:
        query: Natural language query.
        index_name: Name of the saved index.
        top_k: Number of results to return.

    Returns:
        List of chunk dicts with a 'score' field.
    """
    index_path = INDEX_DIR / f"{index_name}.faiss"
    meta_path = INDEX_DIR / f"{index_name}_meta.json"

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
