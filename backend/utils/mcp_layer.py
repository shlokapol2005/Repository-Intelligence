"""
MCP Integration Layer
Provides tool implementations for:
  - GitHub MCP   : Clone repositories from GitHub URLs
  - Filesystem MCP: Targeted safe file reads
  - Code Search MCP: Pattern/symbol search across a repository
  - Terminal MCP  : Run CLI commands (optional, v2)
"""
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import git  # gitpython
from dotenv import load_dotenv

load_dotenv()

CLONED_REPOS_DIR = Path(os.getenv("CLONED_REPOS_DIR", "../cloned-repos")).resolve()
CLONED_REPOS_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
#  GitHub MCP
# ─────────────────────────────────────────────

def github_mcp_clone(github_url: str) -> dict[str, Any]:
    """
    Clone a GitHub repository to /cloned-repos/<repo-name>.
    Returns the local path so the scanner can pick it up.

    Args:
        github_url: e.g. "https://github.com/org/repo"

    Returns:
        {"success": True, "local_path": "...", "repo_name": "..."}
    """
    # Extract repo name from URL
    match = re.search(r"github\.com[/:](.+?)(?:\.git)?$", github_url)
    if not match:
        return {"success": False, "error": "Invalid GitHub URL format."}

    repo_slug = match.group(1).replace("/", "__")
    local_path = CLONED_REPOS_DIR / repo_slug

    if local_path.exists():
        # Repo already cloned — pull latest
        try:
            repo = git.Repo(local_path)
            repo.remotes.origin.pull()
            return {
                "success": True,
                "local_path": str(local_path),
                "repo_name": repo_slug,
                "action": "pulled",
            }
        except Exception as e:
            return {"success": False, "error": f"Pull failed: {e}"}

    # Fresh clone
    try:
        git.Repo.clone_from(github_url, local_path, depth=1)
        return {
            "success": True,
            "local_path": str(local_path),
            "repo_name": repo_slug,
            "action": "cloned",
        }
    except Exception as e:
        return {"success": False, "error": f"Clone failed: {e}"}


# ─────────────────────────────────────────────
#  Filesystem MCP
# ─────────────────────────────────────────────

def filesystem_mcp_read(file_path: str, repo_root: str) -> dict[str, Any]:
    """
    Safely read a single file from within a known repository root.
    Prevents directory traversal attacks.

    Args:
        file_path: Relative or absolute path to the file.
        repo_root: Absolute path to the repository root (trust boundary).

    Returns:
        {"success": True, "content": "...", "lines": N}
    """
    root = Path(repo_root).resolve()
    target = (root / file_path).resolve()

    # Security: ensure target is inside repo_root
    if not str(target).startswith(str(root)):
        return {"success": False, "error": "Access outside repository root is not allowed."}

    if not target.exists() or not target.is_file():
        return {"success": False, "error": f"File not found: {file_path}"}

    try:
        content = target.read_text(encoding="utf-8", errors="ignore")
        return {
            "success": True,
            "path": str(target),
            "relative_path": str(target.relative_to(root)).replace("\\", "/"),
            "content": content,
            "lines": content.count("\n") + 1,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def filesystem_mcp_list(directory: str, repo_root: str) -> dict[str, Any]:
    """
    List all files in a directory within the repository.
    """
    root = Path(repo_root).resolve()
    target = (root / directory).resolve()

    if not str(target).startswith(str(root)):
        return {"success": False, "error": "Access outside repository root is not allowed."}

    if not target.exists() or not target.is_dir():
        return {"success": False, "error": f"Directory not found: {directory}"}

    files = []
    for f in target.rglob("*"):
        if f.is_file():
            files.append(str(f.relative_to(root)).replace("\\", "/"))

    return {"success": True, "files": files, "count": len(files)}


# ─────────────────────────────────────────────
#  Code Search MCP
# ─────────────────────────────────────────────

def code_search_mcp(
    query: str,
    repo_root: str,
    extensions: list[str] | None = None,
    case_sensitive: bool = False,
    max_results: int = 50,
) -> dict[str, Any]:
    """
    Search for a pattern/symbol across all repository files.
    Returns matching file paths, line numbers, and snippets.

    Args:
        query: Text or regex pattern to search for.
        repo_root: Root path of the repository.
        extensions: Optional list of extensions to filter (e.g. [".py", ".js"]).
        case_sensitive: Whether search is case sensitive.
        max_results: Maximum number of matches to return.

    Returns:
        {"matches": [...], "total": N}
    """
    root = Path(repo_root).resolve()
    flags = 0 if case_sensitive else re.IGNORECASE
    matches = []

    try:
        pattern = re.compile(query, flags)
    except re.error as e:
        return {"success": False, "error": f"Invalid regex pattern: {e}"}

    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if extensions and file_path.suffix.lower() not in extensions:
            continue
        # Skip common noise directories
        parts = set(file_path.parts)
        if parts & {"node_modules", "__pycache__", ".git", ".venv", "dist", "build"}:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            for lineno, line in enumerate(content.splitlines(), start=1):
                if pattern.search(line):
                    matches.append({
                        "file": str(file_path.relative_to(root)).replace("\\", "/"),
                        "line": lineno,
                        "snippet": line.strip()[:200],
                    })
                    if len(matches) >= max_results:
                        return {
                            "success": True,
                            "matches": matches,
                            "total": len(matches),
                            "truncated": True,
                        }
        except (OSError, PermissionError):
            continue

    return {
        "success": True,
        "matches": matches,
        "total": len(matches),
        "truncated": False,
    }


# ─────────────────────────────────────────────
#  Terminal MCP (Stub — Phase 2 placeholder, enabled in v2)
# ─────────────────────────────────────────────

ALLOWED_COMMANDS = {"pytest", "npm", "yarn", "tree", "git log", "git status"}


def terminal_mcp_run(command: str, cwd: str) -> dict[str, Any]:
    """
    Run a safe, whitelisted terminal command inside a repository directory.
    Only enabled for approved commands (pytest, npm test, tree, etc.).

    Args:
        command: Command string to execute.
        cwd: Working directory (must be inside a known repo).

    Returns:
        {"success": True, "stdout": "...", "stderr": "...", "returncode": 0}
    """
    # Security: only allow whitelisted prefixes
    cmd_prefix = command.strip().split()[0] if command.strip() else ""
    if not any(command.strip().startswith(c) for c in ALLOWED_COMMANDS):
        return {
            "success": False,
            "error": f"Command '{cmd_prefix}' is not in the allowed list: {ALLOWED_COMMANDS}",
        }

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return {
            "success": True,
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out after 60 seconds."}
    except Exception as e:
        return {"success": False, "error": str(e)}
