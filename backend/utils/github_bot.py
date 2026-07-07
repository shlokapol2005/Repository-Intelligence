"""
github_bot.py — GitHub API client for Code Detective PR Bot.

Handles:
  - Webhook HMAC signature verification (proves the request came from GitHub)
  - Fetching the list of files changed in a Pull Request
  - Posting and updating comments on PRs (avoids duplicates by updating in place)
"""
import hmac
import hashlib
import httpx
from typing import Optional

GITHUB_API = "https://api.github.com"

# Marker embedded in every Code Detective comment.
# Used to find and UPDATE existing comments instead of spamming new ones.
BOT_MARKER = "<!-- code-detective-bot -->"


def verify_webhook_signature(payload_bytes: bytes, signature_header: str, secret: str) -> bool:
    """
    Verify that a webhook payload came from GitHub.
    GitHub signs every request with HMAC-SHA256 using your webhook secret.
    If the signatures don't match, the request is fake — reject it.
    """
    if not signature_header or not secret:
        return not bool(secret)  # if no secret configured, allow all (dev mode)
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), payload_bytes, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


async def get_pr_files(owner: str, repo: str, pr_number: int, token: str) -> list[str]:
    """
    Fetch the list of files changed in a specific Pull Request.
    Returns relative file paths, e.g. ['backend/utils/auth.py', 'models/User.py']
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers, params={"per_page": 100})
        resp.raise_for_status()
        return [f["filename"] for f in resp.json()]


async def _find_existing_comment(
    owner: str, repo: str, pr_number: int, token: str
) -> Optional[int]:
    """
    Search existing PR comments for one posted by Code Detective (identified by BOT_MARKER).
    Returns the comment ID if found, so we can UPDATE it instead of posting a new one.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers=headers, params={"per_page": 100})
        if resp.status_code != 200:
            return None
        for comment in resp.json():
            if BOT_MARKER in comment.get("body", ""):
                return comment["id"]
    return None


async def _post_comment(owner: str, repo: str, pr_number: int, body: str, token: str) -> bool:
    """Post a brand new comment on the PR."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, headers=headers, json={"body": body})
        return resp.status_code == 201


async def _update_comment(
    owner: str, repo: str, comment_id: int, body: str, token: str
) -> bool:
    """Update (edit) an existing comment."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/comments/{comment_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.patch(url, headers=headers, json={"body": body})
        return resp.status_code == 200


async def post_or_update_comment(
    owner: str, repo: str, pr_number: int, body: str, token: str
) -> bool:
    """
    Smart post: if Code Detective has already commented on this PR, UPDATE that comment.
    Otherwise, post a new one. This prevents the bot from spamming multiple comments
    every time new commits are pushed to the PR.
    """
    existing_id = await _find_existing_comment(owner, repo, pr_number, token)
    if existing_id:
        return await _update_comment(owner, repo, existing_id, body, token)
    return await _post_comment(owner, repo, pr_number, body, token)
