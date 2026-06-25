"""
Repository Scanner
Recursively walks a directory, respects .gitignore rules,
and returns a structured list of all code files with metadata.
"""
import os
from pathlib import Path
from typing import Generator
import pathspec


SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "env", "dist", "build", ".next", ".nuxt", "coverage",
    ".idea", ".vscode", ".DS_Store", "eggs", "*.egg-info",
    # Code Detective internals — skip when scanning a cloned copy of this project
    "mock-repo", "cloned-repos", "data",
}

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".go", ".rb", ".php",
    ".html", ".css", ".json", ".yaml", ".yml", ".md",
}


def _load_gitignore(root: Path) -> pathspec.PathSpec | None:
    gitignore_path = root / ".gitignore"
    if gitignore_path.exists():
        with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
            return pathspec.PathSpec.from_lines("gitwildmatch", f.readlines())
    return None


def scan_repository(repo_path: str) -> list[dict]:
    """
    Scan a repository directory and return structured file metadata.

    Args:
        repo_path: Absolute path to the repository root.

    Returns:
        List of file metadata dicts with keys:
            - path: absolute file path
            - relative_path: path relative to repo root
            - extension: file extension
            - size_bytes: file size
            - lines: number of lines
    """
    root = Path(repo_path).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Invalid repository path: {repo_path}")

    gitignore = _load_gitignore(root)
    results = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip directories in-place
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.startswith(".")
        ]

        for filename in filenames:
            file_path = Path(dirpath) / filename
            relative = file_path.relative_to(root)

            # Skip gitignored files
            if gitignore and gitignore.match_file(str(relative)):
                continue

            ext = file_path.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            try:
                size = file_path.stat().st_size
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                lines = content.count("\n") + 1
            except (OSError, PermissionError):
                continue

            results.append({
                "path": str(file_path),
                "relative_path": str(relative).replace("\\", "/"),
                "extension": ext,
                "size_bytes": size,
                "lines": lines,
            })

    return results


def read_file_content(file_path: str) -> str:
    """Read and return the content of a file safely."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except (OSError, PermissionError) as e:
        return f"Error reading file: {e}"
