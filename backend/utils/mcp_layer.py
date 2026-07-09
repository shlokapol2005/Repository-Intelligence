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
import shlex
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

def github_mcp_clone(github_url: str, token: str = "") -> dict[str, Any]:
    """
    Clone a GitHub repository to /cloned-repos/<repo-name>.
    Returns the local path so the scanner can pick it up.

    Args:
        github_url: e.g. "https://github.com/org/repo"
        token:      Optional access token. Required for PRIVATE repos — it's
                    embedded as an x-access-token credential in the clone URL so
                    GitHub App installations can pull repos the public endpoint
                    can't see.

    Returns:
        {"success": True, "local_path": "...", "repo_name": "..."}
    """
    match = re.search(r"github\.com[/:]([^/]+/[^/.]+)(?:\.git)?(?:/tree/(.+?))?/?$", github_url)
    if not match:
        return {"success": False, "error": "Invalid GitHub URL format."}

    org_repo = match.group(1)
    branch = match.group(2)
    if token:
        clone_url = f"https://x-access-token:{token}@github.com/{org_repo}.git"
    else:
        clone_url = f"https://github.com/{org_repo}.git"

    if branch:
        # Use a distinct slug for branches to avoid conflicts
        repo_slug = f"{org_repo.replace('/', '__')}__tree__{branch.replace('/', '_')}"
    else:
        repo_slug = org_repo.replace("/", "__")
        
    local_path = CLONED_REPOS_DIR / repo_slug
    # Tokenless URL we persist as the remote — never leave a credential in .git/config.
    safe_url = f"https://github.com/{org_repo}.git"

    if local_path.exists():
        # Repo already cloned — pull latest
        try:
            repo = git.Repo(local_path)
            if token:
                repo.remotes.origin.set_url(clone_url)
            repo.remotes.origin.pull()
            if token:
                repo.remotes.origin.set_url(safe_url)  # scrub credential
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
        clone_kwargs = {"depth": 1}
        if branch:
            clone_kwargs["branch"] = branch
        repo = git.Repo.clone_from(clone_url, local_path, **clone_kwargs)
        if token:
            # Don't persist the access token in the on-disk git remote.
            try:
                repo.remotes.origin.set_url(safe_url)
            except Exception:
                pass
        return {
            "success": True,
            "local_path": str(local_path),
            "repo_name": repo_slug,
            "action": "cloned",
        }
    except Exception as e:
        return {"success": False, "error": f"Clone failed: {e}"}


_GITHUB_SLUG_RE = re.compile(
    r"github\.com[/:]([^/]+/[^/.]+)(?:\.git)?(?:/tree/(.+?))?/?$"
)


def _github_url_to_slug(github_url: str) -> str | None:
    """Compute the local clone-dir slug for a GitHub URL (mirrors github_mcp_clone)."""
    match = _GITHUB_SLUG_RE.search(github_url)
    if not match:
        return None
    org_repo, branch = match.group(1), match.group(2)
    if branch:
        return f"{org_repo.replace('/', '__')}__tree__{branch.replace('/', '_')}"
    return org_repo.replace("/", "__")


def _slug_to_github_url(slug: str) -> str | None:
    """Reconstruct a GitHub URL from a clone-dir slug (org__repo[/__tree__branch])."""
    slug = slug.strip().strip("/")
    branch = None
    if "__tree__" in slug:
        slug, branch = slug.split("__tree__", 1)
    parts = slug.split("__")
    if len(parts) < 2:
        return None
    org, repo = parts[0], "__".join(parts[1:])
    url = f"https://github.com/{org}/{repo}"
    if branch:
        url += f"/tree/{branch}"
    return url


def resolve_repo(identifier: str, token: str = "") -> str:
    """
    Resolve a repo *identifier* to a local clone path on THIS backend, cloning
    it on demand if it isn't present yet.

    An identifier may be any of:
      - an existing local directory path  (same-machine / already-cloned)
      - a GitHub URL                      (https://github.com/org/repo[/tree/branch])
      - a clone-dir slug                  (org__repo)

    This is what makes deep links portable: the Discord bot embeds a GitHub URL
    (not a machine-specific absolute path), and whichever backend serves the
    link resolves it to its own local copy — cloning if the copy is missing
    (e.g. after an ephemeral-disk restart). Existing clones are returned
    immediately with no network call, so this stays cheap on the hot path.

    Args:
        token: Optional access token, passed through to cloning so a GitHub App
               installation can resolve PRIVATE repos it hasn't cloned yet.
    """
    ident = (identifier or "").strip()
    if not ident:
        raise ValueError("Empty repository identifier.")

    # 1. Already a real local directory? Use it as-is (no network).
    p = Path(ident)
    if p.exists() and p.is_dir():
        return str(p.resolve())

    # 2. Work out the GitHub URL + expected local slug directory.
    url = ident if "github.com" in ident else _slug_to_github_url(ident)
    if not url:
        raise ValueError(f"Could not resolve repository identifier: {identifier}")

    slug = _github_url_to_slug(url)
    if slug:
        local = CLONED_REPOS_DIR / slug
        if local.exists() and local.is_dir():
            return str(local.resolve())  # already cloned — no network

    # 3. Not present locally → clone it now.
    result = github_mcp_clone(url, token=token)
    if result.get("success"):
        return result["local_path"]
    raise ValueError(result.get("error", f"Failed to clone {url}"))


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

    # Security: ensure target is inside repo_root (rejects siblings like "root-secret/")
    if target != root and root not in target.parents:
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

    if target != root and root not in target.parents:
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
    stripped = command.strip()
    if not stripped:
        return {"success": False, "error": "Empty command."}

    try:
        tokens = shlex.split(stripped, posix=(os.name != "nt"))
    except ValueError as e:
        return {"success": False, "error": f"Could not parse command: {e}"}

    if not tokens:
        return {"success": False, "error": "Empty command."}

    # Security: exact token-prefix match against the whitelist only — no
    # substring/startswith matching on the raw string, and no shell involved,
    # so "git log; rm -rf /" cannot slip through or be interpreted by a shell.
    allowed = any(
        tokens[: len(prefix.split())] == prefix.split()
        for prefix in ALLOWED_COMMANDS
    )
    if not allowed:
        return {
            "success": False,
            "error": f"Command '{tokens[0]}' is not in the allowed list: {sorted(ALLOWED_COMMANDS)}",
        }

    cwd_path = Path(cwd).resolve()
    if not cwd_path.is_dir():
        return {"success": False, "error": f"cwd is not a valid directory: {cwd}"}

    try:
        result = subprocess.run(
            tokens,
            shell=False,
            cwd=str(cwd_path),
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
    except FileNotFoundError:
        return {"success": False, "error": f"Command not found: {tokens[0]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
