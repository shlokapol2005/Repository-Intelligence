"""
state.py — Channel-bound repository state.

Maps Discord channel_id → {repo_path, index_name, repo_name}
Persists to state.json so bot restarts don't wipe the loaded repos.
"""
import json
from pathlib import Path

_STATE_FILE = Path(__file__).parent / "state.json"

# In-memory store: {channel_id (str) → {repo_path, index_name, repo_name}}
_state: dict[str, dict] = {}


def _load() -> None:
    """Load persisted state from disk on startup."""
    global _state
    if _STATE_FILE.exists():
        try:
            _state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _state = {}


def _save() -> None:
    """Write current state to disk."""
    _STATE_FILE.write_text(json.dumps(_state, indent=2), encoding="utf-8")


def set_repo(
    channel_id: int,
    repo_path: str,
    index_name: str,
    repo_name: str,
    github_url: str = "",
) -> None:
    """Bind a repo to a channel and persist.

    github_url is the portable identifier used for deep links (so they work on
    any backend, not just the machine that cloned the repo). Falls back to the
    slug/path where absent for older bindings.
    """
    _state[str(channel_id)] = {
        "repo_path": repo_path,
        "index_name": index_name,
        "repo_name": repo_name,
        "github_url": github_url,
    }
    _save()


def get_repo(channel_id: int) -> dict | None:
    """Return the repo bound to this channel, or None."""
    return _state.get(str(channel_id))


def clear_repo(channel_id: int) -> None:
    """Remove the repo binding for this channel."""
    _state.pop(str(channel_id), None)
    _save()


# Auto-load on import
_load()
