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
import asyncio
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from fastapi.responses import JSONResponse

from utils.github_bot import (
    verify_webhook_signature,
    get_pr_files,
    post_or_update_comment,
    BOT_MARKER,
)
from utils.github_app import get_token, installation_id_from_payload, is_app_configured
from utils.mcp_layer import resolve_repo
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
    Find the local clone of a GitHub repo by its full_name (e.g. 'octocat/hello-world')
    using a case-insensitive match (since Linux is case-sensitive but URLs aren't).
    """
    safe_name = full_name.replace("/", "__").lower()
    fallback_name = full_name.split("/")[-1].lower()

    if not _CLONED_REPOS_DIR.exists():
        return None

    for item in _CLONED_REPOS_DIR.iterdir():
        if item.is_dir():
            item_lower = item.name.lower()
            if item_lower == safe_name or item_lower == fallback_name:
                return item
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


async def _process_pr_event(
    owner: str,
    repo_name: str,
    repo_full_name: str,
    pr_number: int,
    pr_title: str,
    pr_author: str,
    installation_id: Optional[int],
) -> None:
    """
    Heavy PR analysis — runs in the BACKGROUND after we've already 202'd GitHub.

    GitHub expects a webhook response within ~10s and marks slow deliveries as
    failed. Minting the installation token, cloning the repo, building the
    dependency graph, and calling the GitHub API can easily exceed that, so all
    of it happens here, off the request path. Failures are logged (we can no
    longer surface them via the HTTP response).
    """
    # Acquire a token: GitHub App installation token, or the static PAT.
    try:
        token = await get_token(installation_id)
    except Exception as e:
        print(f"[webhook] failed to obtain token for {repo_full_name}: {e}")
        return
    if not token:
        print(f"[webhook] no GitHub token available for {repo_full_name} — skipping.")
        return

    try:
        changed_files = await get_pr_files(owner, repo_name, pr_number, token)
    except Exception as e:
        print(f"[webhook] get_pr_files failed for {repo_full_name}#{pr_number}: {e}")
        return

    total_changed = len(changed_files)

    # Resolve the repo to a local clone — cloning on demand (with the token so
    # private repos work). No manual "/repobot load" required for the App.
    repo_url = f"https://github.com/{repo_full_name}"
    try:
        local_repo = await asyncio.to_thread(resolve_repo, repo_url, token)
    except Exception as e:
        print(f"[webhook] could not clone/resolve {repo_full_name}: {e}")
        try:
            await post_or_update_comment(
                owner, repo_name, pr_number,
                _build_not_loaded_comment(repo_full_name), token,
            )
        except Exception:
            pass
        return

    # Run impact analysis for each changed source file (cap at 10)
    source_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}
    source_files = [
        f for f in changed_files
        if Path(f).suffix.lower() in source_exts
    ][:10]

    try:
        # get_or_build_graph parses/builds — blocking, so run off the loop.
        cache = await asyncio.to_thread(get_or_build_graph, str(local_repo))
        G = cache["G"]
        file_results = []
        for fname in source_files:
            impact = get_impact(G, fname)
            file_results.append({
                "file":   fname,
                "impact": impact if "error" not in impact else None,
                "error":  impact.get("error"),
            })
    except Exception as e:
        print(f"[webhook] graph analysis failed for {repo_full_name}#{pr_number}: {e}")
        return

    comment_body = _build_impact_comment(
        pr_title, pr_number, pr_author,
        repo_full_name, file_results,
        changed_files, total_changed,
    )

    try:
        await post_or_update_comment(
            owner, repo_name, pr_number, comment_body, token
        )
    except Exception as e:
        print(f"[webhook] failed to post impact comment for {repo_full_name}#{pr_number}: {e}")


@router.post("/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event:      Optional[str] = Header(None),
    x_hub_signature_256: Optional[str] = Header(None),
):
    """
    Receive GitHub webhook events. Validate fast, then defer the heavy PR
    analysis to a background task and return 202 immediately — so GitHub always
    gets a prompt response and never marks the delivery as timed-out.
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
    installation_id = installation_id_from_payload(payload)

    # ── 4. Ensure SOME auth path exists (App install OR static PAT) ───────────
    if not is_app_configured() and not os.getenv("GITHUB_TOKEN", "").strip():
        raise HTTPException(
            status_code=500,
            detail="No GitHub auth configured (need a GitHub App install or GITHUB_TOKEN).",
        )

    # ── 5. Defer heavy work; respond at once so GitHub never times out ────────
    background_tasks.add_task(
        _process_pr_event,
        owner, repo_name, repo_full_name,
        pr_number, pr_title, pr_author, installation_id,
    )
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "pr_number": pr_number, "action": action},
    )
