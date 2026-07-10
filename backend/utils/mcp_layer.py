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

def _friendly_git_error(err_text: str, org_repo: str) -> str:
    """Translate a raw git clone/pull failure into a message a user understands."""
    low = err_text.lower()
    if "not found" in low or "repository not found" in low:
        return (
            f"Repository '{org_repo}' not found. Check the owner/name — and note "
            f"this works with PUBLIC repos only. (Private repos are supported via "
            f"the GitHub App, not the web app or Discord bot.)"
        )
    if any(s in low for s in (
        "authentication failed", "invalid username or password",
        "could not read username", "permission denied", "403",
    )):
        return (
            f"Can't access '{org_repo}' — it looks private. Only PUBLIC repos work "
            f"here; install the GitHub App for private-repo analysis."
        )
    if any(s in low for s in ("timed out", "timeout", "unable to access", "could not resolve host")):
        return f"Cloning '{org_repo}' failed (network / timeout). Try again shortly."
    return f"Could not clone '{org_repo}': {err_text[:200]}"


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
    org_repo, branch = _parse_github_repo(github_url)
    if not org_repo:
        return {
            "success": False,
            "error": "Invalid GitHub URL. Use https://github.com/<owner>/<repo>.",
        }

    if token:
        clone_url = f"https://x-access-token:{token}@github.com/{org_repo}.git"
    else:
        clone_url = f"https://github.com/{org_repo}.git"

    repo_slug = _slug_from(org_repo, branch)
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
            return {"success": False, "error": _friendly_git_error(str(e), org_repo)}

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
        return {"success": False, "error": _friendly_git_error(str(e), org_repo)}


def _parse_github_repo(github_url: str):
    """
    Extract (org/repo, branch|None) from whatever the user typed — robustly.

    Accepts:
      - full URLs:   https://github.com/owner/repo[.git][/tree/branch][?...]
      - SSH URLs:    git@github.com:owner/repo.git
      - extra paths: .../owner/repo/blob/main/file.py  (trailing junk ignored)
      - shorthand:   owner/repo            ← just the repo name, no github.com

    Handles trailing `.git`, query strings/fragments, whitespace, and repo
    names with dots/hyphens (e.g. `socket.io`, `next.js`). Returns (None, None)
    when it isn't recognizable.
    """
    url = (github_url or "").strip()

    m = re.search(r"github\.com[/:]([^/\s]+)/([^/\s?#]+)", url)
    if m:
        org, repo = m.group(1), m.group(2)
        branch_m = re.search(r"/tree/([^/\s?#]+)", url)
        branch = branch_m.group(1) if branch_m else None
    else:
        # Shorthand: bare "owner/repo" with no host — assume GitHub.
        short = re.fullmatch(r"([\w.-]+)/([\w.-]+)", url)
        if not short:
            return None, None
        org, repo = short.group(1), short.group(2)
        branch = None

    if repo.endswith(".git"):
        repo = repo[:-4]
    return f"{org}/{repo}", branch


def _slug_from(org_repo: str, branch: str | None) -> str:
    """Compute the local clone-dir slug from org/repo (+ optional branch)."""
    if branch:
        return f"{org_repo.replace('/', '__')}__tree__{branch.replace('/', '_')}"
    return org_repo.replace("/", "__")


def _github_url_to_slug(github_url: str) -> str | None:
    """Compute the local clone-dir slug for a GitHub URL (mirrors github_mcp_clone)."""
    org_repo, branch = _parse_github_repo(github_url)
    if not org_repo:
        return None
    return _slug_from(org_repo, branch)


def _slug_to_github_url(slug: str) -> str | None:
    """Reconstruct a GitHub URL from a clone-dir slug (org__repo[/__tree__branch])."""
    slug = slug.strip().strip("/")
    # A real slug never contains path separators. Reject file paths so we don't
    # mangle e.g. "/opt/render/.../org__repo" into a bogus github URL.
    if "/" in slug or "\\" in slug:
        return None
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


def _pull_latest(local_path: Path, token: str = "") -> None:
    """
    Best-effort `git pull` of an existing clone so analysis reflects the current
    code (not a stale snapshot). Injects the token for private pulls and scrubs
    it from the remote afterwards. Failures are swallowed — a stale copy beats a
    crash.
    """
    try:
        repo = git.Repo(local_path)
        origin = repo.remotes.origin
        current_url = next(iter(origin.urls), "")
        org_repo, _ = _parse_github_repo(current_url)
        if token and org_repo:
            origin.set_url(f"https://x-access-token:{token}@github.com/{org_repo}.git")
            origin.pull()
            origin.set_url(f"https://github.com/{org_repo}.git")  # scrub credential
        else:
            origin.pull()
    except Exception:
        pass


def resolve_repo(identifier: str, token: str = "", refresh: bool = False) -> str:
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
        token:   Optional access token, passed through to cloning so a GitHub App
                 installation can resolve PRIVATE repos it hasn't cloned yet.
        refresh: When True, `git pull` an existing clone so analysis reflects the
                 latest code. Off by default to keep the hot path cheap; the
                 PR/push webhook turns it on so it never analyzes stale code.
    """
    ident = (identifier or "").strip()
    if not ident:
        raise ValueError("Empty repository identifier.")

    # 1. Already a real local directory? Use it as-is (pull first if refreshing).
    p = Path(ident)
    if p.exists() and p.is_dir():
        if refresh:
            _pull_latest(p, token)
        return str(p.resolve())

    # 2. Not an existing dir → work out the GitHub URL.
    #    If it's a filesystem PATH that no longer exists (e.g. the clone was wiped
    #    on an ephemeral-disk restart), recover the repo from the clone-dir NAME:
    #    its basename is the "org__repo" slug, which we turn back into a URL and
    #    re-clone. This makes the web app self-heal after a Render restart instead
    #    of choking on a dead path.
    if "github.com" in ident:
        url = ident
    else:
        candidate = Path(ident).name if ("/" in ident or "\\" in ident) else ident
        url = _slug_to_github_url(candidate)
    if not url:
        raise ValueError(
            "Repository not found on this server (it may have been cleared on a "
            f"restart). Re-load it. [{identifier}]"
        )

    slug = _github_url_to_slug(url)
    if slug:
        local = CLONED_REPOS_DIR / slug
        if local.exists() and local.is_dir():
            if refresh:
                _pull_latest(local, token)
            return str(local.resolve())

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
