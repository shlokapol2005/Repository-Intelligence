"""
webhook.py — GitHub Webhook Handler for Code Detective PR Bot.

Flow:
  1. GitHub fires POST /webhook/github when a PR is opened/updated
  2. We verify the HMAC signature (proves it's really from GitHub)
  3. We get the list of files changed in the PR via GitHub API
  4. We find the local clone of the repo in cloned-repos/
  5. We run impact_analysis for each changed file
  6. We build a beautiful markdown comment with the blast radius
  7. We post (or update) the comment on the PR via GitHub API

Dev setup:
  - Set GITHUB_TOKEN and GITHUB_WEBHOOK_SECRET in backend/.env
  - Use ngrok to expose localhost:8000 to GitHub during development:
      ngrok http 8000
  - Set webhook URL in GitHub repo settings to: https://<ngrok-url>/webhook/github
"""
import os
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header

from utils.github_bot import (
    verify_webhook_signature,
    get_pr_files,
    post_or_update_comment,
    BOT_MARKER,
)
from utils.agents import get_or_build_graph
from utils.graph_builder import get_impact

router = APIRouter()

# Where cloned repos are stored (matches backend/.env CLONED_REPOS_DIR)
_CLONED_REPOS_DIR = Path(
    os.getenv("CLONED_REPOS_DIR", "../cloned-repos")
).resolve()

RISK_EMOJI = {
    "Low":      "🟢",
    "Medium":   "🟡",
    "High":     "🔴",
    "Critical": "🚨",
}

RISK_ORDER = ["Low", "Medium", "High", "Critical"]


def _find_local_repo(full_name: str) -> Optional[Path]:
    """
    Find the local clone of a GitHub repo by its full_name (e.g. 'octocat/hello-world').

    Naming conventions tried (in order):
      1. cloned-repos/octocat__hello-world   ← Code Detective clone convention
      2. cloned-repos/hello-world            ← just the repo name
    """
    safe_name = full_name.replace("/", "__")
    for candidate in [
        _CLONED_REPOS_DIR / safe_name,
        _CLONED_REPOS_DIR / full_name.split("/")[-1],
    ]:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def _build_not_loaded_comment(repo_full_name: str) -> str:
    """Comment to post when the repo hasn't been loaded into Code Detective yet."""
    return f"""{BOT_MARKER}
## 🔍 Code Detective — Impact Analysis

⚠️ **This repository isn't loaded yet.**

To enable automatic PR impact analysis, load the repo once:

```
/repobot load https://github.com/{repo_full_name}
```

After that, every PR will automatically get an impact report like this one.

---
<sub>🤖 Powered by **Code Detective**</sub>
"""


def _build_impact_comment(
    pr_title: str,
    pr_number: int,
    pr_author: str,
    repo_full_name: str,
    file_results: list[dict],
    changed_files: list[str],
    total_changed: int,
) -> str:
    """Build the full markdown impact analysis comment for the PR."""

    # ── Aggregate across all changed files ────────────────────────────────────
    all_affected: set[str] = set()
    all_routes:   set[str] = set()
    overall_risk = "Low"

    for r in file_results:
        if r.get("impact"):
            imp = r["impact"]
            all_affected.update(imp.get("affected_files", []))
            all_routes.update(imp.get("affected_routes", []))
            risk = imp.get("risk", "Low")
            if RISK_ORDER.index(risk) > RISK_ORDER.index(overall_risk):
                overall_risk = risk

    risk_emoji = RISK_EMOJI.get(overall_risk, "⚪")

    # ── Per-file table ─────────────────────────────────────────────────────────
    table_rows = []
    for r in file_results:
        fname = r["file"]
        short = fname if len(fname) <= 55 else "…" + fname[-52:]
        if r.get("error") or not r.get("impact"):
            table_rows.append(f"| `{short}` | ⚪ Not in graph | — | — |")
        else:
            imp   = r["impact"]
            risk  = imp.get("risk", "Low")
            count = imp.get("count", 0)
            routes = len(imp.get("affected_routes", []))
            emoji  = RISK_EMOJI.get(risk, "⚪")
            table_rows.append(
                f"| `{short}` | {emoji} {risk} | {count} | {routes} |"
            )

    # Note if we capped the analysis
    truncation_note = ""
    if total_changed > len(file_results):
        truncation_note = (
            f"\n> ℹ️ This PR changed **{total_changed} files** total. "
            f"Analysis shown for the **{len(file_results)} most impactful** files.\n"
        )

    # ── Affected files section ─────────────────────────────────────────────────
    if all_affected:
        shown     = sorted(all_affected)[:30]
        leftover  = len(all_affected) - len(shown)
        file_list = "\n".join(f"- `{f}`" for f in shown)
        if leftover > 0:
            file_list += f"\n- _...and {leftover} more_"
        affected_section = (
            f"<details>\n"
            f"<summary>📁 Click to expand — {len(all_affected)} affected files</summary>\n\n"
            f"{file_list}\n\n</details>"
        )
    else:
        affected_section = "_No downstream files affected. This change is self-contained._ ✅"

    # ── API routes section ─────────────────────────────────────────────────────
    if all_routes:
        routes_section = "\n".join(f"- `{r}`" for r in sorted(all_routes))
    else:
        routes_section = "_No API routes affected._"

    return f"""{BOT_MARKER}
## 🔍 Code Detective — PR Impact Analysis

**#{pr_number} — {pr_title}** by @{pr_author}
{truncation_note}
### 📊 Per-File Breakdown

| File Changed | Risk | Files Affected | API Routes |
|---|:---:|:---:|:---:|
{chr(10).join(table_rows)}

---

### 💥 Total Blast Radius

| | |
|---|---|
| **Overall Risk** | {risk_emoji} **{overall_risk}** |
| **Downstream files affected** | **{len(all_affected)}** |
| **API routes at risk** | **{len(all_routes)}** |
| **Files changed in this PR** | **{total_changed}** |

### 🔌 API Routes at Risk
{routes_section}

### 📁 Affected Files
{affected_section}

---

<sub>🤖 Powered by **[Code Detective](https://github.com/shlokapol2005/Repository-Intelligence)** · Updates automatically on each push to this PR</sub>
"""


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event:      Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
):
    """
    Receive and process GitHub webhook events.

    GitHub sends this endpoint a POST request whenever a PR is opened,
    updated (new commits pushed), or reopened. We analyze the changed files
    and post an impact analysis comment on the PR.
    """
    payload_bytes = await request.body()

    # ── 1. Verify the request is really from GitHub ────────────────────────────
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    if not verify_webhook_signature(payload_bytes, x_hub_signature_256 or "", secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # ── 2. Only handle pull_request events ────────────────────────────────────
    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    try:
        payload = json.loads(payload_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    action = payload.get("action", "")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "action": action}

    # ── 3. Extract PR metadata ─────────────────────────────────────────────────
    pr             = payload.get("pull_request", {})
    repo_meta      = payload.get("repository", {})
    pr_number      = pr.get("number")
    pr_title       = pr.get("title", "Untitled PR")
    pr_author      = pr.get("user", {}).get("login", "unknown")
    repo_full_name = repo_meta.get("full_name", "")

    if not repo_full_name or not pr_number:
        raise HTTPException(status_code=400, detail="Missing repo or PR info in payload")

    owner, repo_name = repo_full_name.split("/", 1)

    # ── 4. Validate GitHub token ───────────────────────────────────────────────
    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        return {"status": "error", "message": "GITHUB_TOKEN not set in .env"}

    # ── 5. Get changed files from GitHub API ──────────────────────────────────
    try:
        changed_files = await get_pr_files(owner, repo_name, pr_number, github_token)
    except Exception as e:
        return {"status": "error", "message": f"Could not fetch PR files: {e}"}

    total_changed = len(changed_files)

    # ── 6. Find local repo clone ───────────────────────────────────────────────
    local_repo = _find_local_repo(repo_full_name)
    if not local_repo:
        await post_or_update_comment(
            owner, repo_name, pr_number,
            _build_not_loaded_comment(repo_full_name),
            github_token,
        )
        return {"status": "repo_not_loaded", "repo": repo_full_name}

    # ── 7. Run impact analysis for each changed file (cap at 10) ──────────────
    source_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}
    source_files = [
        f for f in changed_files
        if Path(f).suffix.lower() in source_exts
    ][:10]

    file_results = []
    try:
        cache = get_or_build_graph(str(local_repo))
        G     = cache["G"]

        for fname in source_files:
            impact = get_impact(G, fname)
            file_results.append({
                "file":   fname,
                "impact": impact if "error" not in impact else None,
                "error":  impact.get("error"),
            })

    except Exception as e:
        return {"status": "error", "message": f"Graph analysis failed: {e}"}

    # ── 8. Build and post the comment ─────────────────────────────────────────
    comment_body = _build_impact_comment(
        pr_title, pr_number, pr_author,
        repo_full_name, file_results,
        changed_files, total_changed,
    )

    try:
        success = await post_or_update_comment(
            owner, repo_name, pr_number, comment_body, github_token
        )
    except Exception as e:
        return {"status": "error", "message": f"Failed to post comment: {e}"}

    return {
        "status":          "success",
        "pr_number":       pr_number,
        "files_analyzed":  len(file_results),
        "total_changed":   total_changed,
        "comment_posted":  success,
    }
