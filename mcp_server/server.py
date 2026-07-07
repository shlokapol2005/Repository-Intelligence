"""
Code Detective — MCP Server
============================
A true Model Context Protocol server exposing Code Detective's full
intelligence engine to Claude Desktop, Cursor, and any MCP-compatible client.

Transport: stdio (runs as a subprocess — no HTTP port needed)

Tools exposed:
  1. scan_repo          — Scan a local path, parse all files, build graph
  2. build_graph        — Return the cached dependency graph as JSON
  3. impact_analysis    — Find all files that break if a target file changes
  4. dead_code          — Detect files nobody imports (potential dead code)
  5. explain_file       — AI-powered explanation of any file in the repo
  6. search_code        — Regex / symbol search across the entire codebase
  7. clone_repo         — Clone a GitHub repository to local storage
  8. ask_repo           — Natural-language Q&A against the repository

Usage:
  cd C:/Users/Shloka Pol/OneDrive/Desktop/code-Detective(p)
  python mcp_server/server.py

Register in Claude Desktop (claude_desktop_config.json):
  {
    "mcpServers": {
      "code-detective": {
        "command": "python",
        "args": ["mcp_server/server.py"],
        "cwd": "C:/Users/Shloka Pol/OneDrive/Desktop/code-Detective(p)"
      }
    }
  }
"""

import sys
import os
import json
import re
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
# Ensure the backend package is importable when server.py runs from repo root
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ── Env ───────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(_BACKEND_DIR / ".env")

# ── MCP SDK ───────────────────────────────────────────────────────────────────
from mcp.server.fastmcp import FastMCP

# ── Backend utilities ─────────────────────────────────────────────────────────
from utils.mcp_layer import (
    github_mcp_clone,
    filesystem_mcp_read,
    code_search_mcp,
)
from utils.graph_builder import (
    get_impact,
    detect_dead_code,
)
from utils.agents import get_or_build_graph, invalidate_graph
from utils.github_bot import get_pr_files

# ── Gemini AI (used by explain_file and ask_repo) ─────────────────────────────
import google.generativeai as genai
genai.configure(api_key=os.getenv("GEMINI_API_KEY", ""))
_llm = genai.GenerativeModel("gemini-2.5-flash")


# ─────────────────────────────────────────────────────────────────────────────
#  FastMCP server instance
# ─────────────────────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="code-detective",
    instructions=(
        "Code Detective gives you deep intelligence about any codebase. "
        "Start by cloning a repo with clone_repo() or providing a local path, "
        "then scan it with scan_repo(), and use the analysis tools "
        "(impact_analysis, dead_code, ask_repo, explain_file) to understand, "
        "debug, and reason about the code architecture."
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
#  TOOL 1 — clone_repo
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def clone_repo(github_url: str) -> str:
    """
    Clone a GitHub repository to local storage.

    Args:
        github_url: Full GitHub URL, e.g. 'https://github.com/org/repo'

    Returns:
        JSON string with local_path, repo_name, and action ('cloned' or 'pulled').

    Example:
        clone_repo('https://github.com/fastapi/fastapi')
    """
    result = github_mcp_clone(github_url)
    if not result.get("success"):
        return f"ERROR: Clone failed: {result.get('error', 'Unknown error')}"

    return json.dumps({
        "status":     "success",
        "local_path": result["local_path"],
        "repo_name":  result["repo_name"],
        "action":     result.get("action", "cloned"),
        "message":    (
            f"Repository '{result['repo_name']}' is ready at {result['local_path']}. "
            "Now call scan_repo() with this local_path to analyze it."
        ),
    }, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
#  TOOL 2 — scan_repo
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def scan_repo(repo_path: str) -> str:
    """
    Scan a repository: parse all source files, extract classes, functions,
    API routes, and build the dependency graph. Results are cached.

    Args:
        repo_path: Absolute local path to the repository root.
                   Use clone_repo() first if you have a GitHub URL.

    Returns:
        JSON summary: file count, import count, language breakdown, top files.

    Example:
        scan_repo('C:/path/to/cloned-repos/org__reponame')
    """
    try:
        invalidate_graph(repo_path)  # force fresh scan
        cache = get_or_build_graph(repo_path)
        G = cache["G"]

        lang_counts: dict[str, int] = {}
        for _, data in G.nodes(data=True):
            lang = data.get("language", "unknown")
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

        top_files = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:10]

        return json.dumps({
            "status":              "success",
            "repo_path":           repo_path,
            "total_files":         G.number_of_nodes(),
            "total_import_edges":  G.number_of_edges(),
            "languages":           lang_counts,
            "top_connected_files": top_files,
            "message": (
                f"Scanned {G.number_of_nodes()} files and found "
                f"{G.number_of_edges()} import relationships. "
                "Use build_graph(), impact_analysis(), dead_code(), or ask_repo() next."
            ),
        }, indent=2)

    except Exception as e:
        return f"ERROR: Scan failed: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  TOOL 3 — build_graph
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def build_graph(repo_path: str, max_nodes: int = 50) -> str:
    """
    Return the full dependency graph for a repository.
    Nodes = source files. Edges = import relationships.

    Each node carries: language, classes, functions, api_routes, lines,
    size_bytes, in_degree (imported by N files), out_degree (imports N files).

    Args:
        repo_path:  Absolute local path to the repository root.
        max_nodes:  Limit to the N most-connected nodes (default 50).
                    Pass 0 to return all nodes (may be very large).

    Returns:
        JSON with nodes[], edges[], and stats.

    Example:
        build_graph('C:/path/to/repo', max_nodes=30)
    """
    try:
        cache = get_or_build_graph(repo_path)
        G     = cache["G"]
        gdict = cache["dict"]

        if max_nodes and max_nodes > 0:
            top = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:max_nodes]
            top_set    = set(top)
            nodes_out  = [n for n in gdict["nodes"] if n["id"] in top_set]
            edges_out  = [e for e in gdict["edges"]
                          if e["source"] in top_set and e["target"] in top_set]
            stats = {
                **gdict["stats"],
                "showing_nodes": len(nodes_out),
                "showing_edges": len(edges_out),
                "note": f"Showing top {max_nodes} most-connected nodes. Pass max_nodes=0 for all.",
            }
        else:
            nodes_out = gdict["nodes"]
            edges_out = gdict["edges"]
            stats     = gdict["stats"]

        return json.dumps({
            "nodes": nodes_out,
            "edges": edges_out,
            "stats": stats,
        }, indent=2)

    except Exception as e:
        return f"ERROR: Graph build failed: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  TOOL 4 — impact_analysis
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def impact_analysis(repo_path: str, target_file: str) -> str:
    """
    Find every file that would be affected if target_file changes.
    Also reports which API routes would be impacted and assigns a risk level.

    Risk levels:
      Low      — 0 dependents
      Medium   — 1–3 dependents
      High     — 4–10 dependents
      Critical — 11+ dependents

    Args:
        repo_path:   Absolute path to the repository root.
        target_file: Relative path to the file within the repo,
                     e.g. 'backend/utils/auth.py' or 'src/database/connection.ts'

    Returns:
        JSON with affected_files, affected_routes, risk level, and count.

    Example:
        impact_analysis('C:/path/to/repo', 'src/utils/database.py')
    """
    try:
        cache  = get_or_build_graph(repo_path)
        G      = cache["G"]
        result = get_impact(G, target_file)

        if "error" in result:
            sample_nodes = list(G.nodes())[:20]
            return (
                f"ERROR: {result['error']}\n\n"
                f"Available files (first 20):\n" +
                "\n".join(f"  - {n}" for n in sample_nodes)
            )

        risk_badge = {
            "Low":      "LOW RISK",
            "Medium":   "MEDIUM RISK",
            "High":     "HIGH RISK",
            "Critical": "CRITICAL RISK",
        }
        result["risk_badge"] = risk_badge.get(result["risk"], result["risk"])
        result["summary"] = (
            f"[{result['risk_badge']}] Changing '{target_file}' directly or "
            f"indirectly affects {result['affected_count']} files "
            f"and {len(result['affected_routes'])} API routes."
        )

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"ERROR: Impact analysis failed: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  TOOL 5 — dead_code
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def dead_code(repo_path: str) -> str:
    """
    Detect potentially unused files — files that nothing in the repo imports.

    Known entrypoints (main.py, index.js, app.py, etc.) and files declaring
    API routes are automatically excluded from the dead code list.

    Args:
        repo_path: Absolute path to the repository root.

    Returns:
        JSON with unused_files (name, language, functions, classes) and count.

    Example:
        dead_code('C:/path/to/repo')
    """
    try:
        cache  = get_or_build_graph(repo_path)
        G      = cache["G"]
        result = detect_dead_code(G)

        total = G.number_of_nodes()
        count = result["count"]
        result["total_files"] = total
        result["percentage"]  = round((count / total * 100), 1) if total > 0 else 0.0

        if count == 0:
            result["summary"] = "No dead code detected. Every file is imported somewhere."
        else:
            result["summary"] = (
                f"{count} of {total} files ({result['percentage']}%) appear unused. "
                "They may be legacy code, standalone scripts, or test fixtures."
            )

        return json.dumps(result, indent=2)

    except Exception as e:
        return f"ERROR: Dead code detection failed: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  TOOL 6 — explain_file
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def explain_file(repo_path: str, file_path: str) -> str:
    """
    Use Gemini AI to explain what a file does — its purpose, key classes,
    functions, patterns used, and how it fits in the larger architecture.

    Args:
        repo_path: Absolute path to the repository root.
        file_path: Relative path to the file, e.g. 'src/auth/middleware.ts'

    Returns:
        Markdown-formatted explanation of the file.

    Example:
        explain_file('C:/path/to/repo', 'backend/utils/graph_builder.py')
    """
    try:
        read_result = filesystem_mcp_read(file_path, repo_path)
        if not read_result.get("success"):
            return f"ERROR: Could not read file: {read_result.get('error')}"

        content  = read_result["content"]
        rel_path = read_result.get("relative_path", file_path)
        lines    = read_result.get("lines", 0)

        # Enrich with graph context if available
        graph_context = ""
        try:
            cache = get_or_build_graph(repo_path)
            G     = cache["G"]
            if rel_path in G:
                in_deg    = G.in_degree(rel_path)
                out_deg   = G.out_degree(rel_path)
                importers = list(G.predecessors(rel_path))[:5]
                imports   = list(G.successors(rel_path))[:5]
                graph_context = (
                    f"\n\nDependency Graph Context:\n"
                    f"- Imported by {in_deg} files: {importers or 'none'}\n"
                    f"- Imports {out_deg} files: {imports or 'none'}"
                )
        except Exception:
            pass

        prompt = f"""You are a senior software engineer performing a code review.
Analyze the file below and provide a clear, structured technical explanation.

File: {rel_path}
Lines: {lines}{graph_context}

--- FILE CONTENT ---
{content[:6000]}
--- END ---

Provide the following sections in markdown:

## Purpose
What does this file do and why does it exist?

## Key Components
List the main classes, functions, or exports and what each one does (1-2 sentences each).

## Architecture Role
How does this file fit in the larger system? (e.g. entrypoint, middleware, utility, data model, router)

## Patterns & Techniques
Notable design patterns, algorithms, or techniques used.

## Potential Issues
Any code smells, potential bugs, or improvement opportunities you notice.
Be specific and actionable."""

        response = _llm.generate_content(prompt)
        return response.text

    except Exception as e:
        return f"ERROR: explain_file failed: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  TOOL 7 — search_code
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def search_code(
    repo_path:      str,
    query:          str,
    extensions:     str  = "",
    case_sensitive: bool = False,
    max_results:    int  = 30,
) -> str:
    """
    Search for a pattern, symbol, or regex across all files in a repository.
    Returns matching file paths, line numbers, and code snippets.

    Args:
        repo_path:      Absolute path to the repository root.
        query:          Text or regex pattern to search for.
        extensions:     Comma-separated extensions to filter, e.g. '.py,.ts'
                        Leave empty to search all source files.
        case_sensitive: Whether search is case-sensitive (default: False).
        max_results:    Max number of matches to return (default: 30).

    Returns:
        JSON with matches (file, line number, snippet) and total count.

    Examples:
        search_code('C:/path/to/repo', 'async def authenticate', '.py')
        search_code('C:/path/to/repo', 'TODO|FIXME|HACK', '.py,.ts,.js')
        search_code('C:/path/to/repo', 'console\\.error', '.js,.ts')
    """
    try:
        ext_list = None
        if extensions.strip():
            ext_list = [e.strip() for e in extensions.split(",") if e.strip()]

        result = code_search_mcp(
            query=query,
            repo_root=repo_path,
            extensions=ext_list,
            case_sensitive=case_sensitive,
            max_results=max_results,
        )

        if not result.get("success"):
            return f"ERROR: Search failed: {result.get('error')}"

        matches   = result.get("matches", [])
        total     = result.get("total", 0)
        truncated = result.get("truncated", False)

        return json.dumps({
            "query":     query,
            "total":     total,
            "truncated": truncated,
            "matches":   matches,
            "summary":   (
                f"Found {total} matches for '{query}'"
                + (" (results truncated, increase max_results to see more)" if truncated else "")
            ),
        }, indent=2)

    except Exception as e:
        return f"ERROR: Code search failed: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  TOOL 8 — ask_repo
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
def ask_repo(repo_path: str, question: str) -> str:
    """
    Ask a natural-language question about any repository.
    Searches the codebase for relevant files and uses Gemini AI to answer.

    Best for questions like:
      - "Where is authentication handled?"
      - "How does the payment processing flow work?"
      - "Which file handles database connections?"
      - "What does the UserProfile class do?"
      - "How are API routes structured in this project?"

    Args:
        repo_path: Absolute path to the repository root.
        question:  Natural-language question about the codebase.

    Returns:
        A detailed, markdown-formatted answer grounded in the actual source code.

    Example:
        ask_repo('C:/path/to/repo', 'How does user authentication work?')
    """
    try:
        # Extract search keywords from question
        stop = {
            "what", "where", "when", "which", "who", "does", "this", "that",
            "have", "with", "from", "into", "about", "your", "their", "there",
            "here", "some", "then", "than", "more", "just", "been", "will",
            "how", "the", "and", "for", "are", "can", "show", "tell", "find",
            "explain", "list", "give", "please", "work", "works", "used",
        }
        tokens   = re.sub(r"[^a-z0-9_]", " ", question.lower()).split()
        keywords = [t for t in tokens if len(t) >= 4 and t not in stop][:6]

        if not keywords:
            return (
                "Could not extract search keywords from your question. "
                "Try using search_code() with specific function or class names."
            )

        # Gather relevant files via keyword search
        seen_files: set[str] = set()
        context_blocks: list[str] = []

        for kw in keywords:
            result = code_search_mcp(
                query=kw,
                repo_root=repo_path,
                extensions=[".py", ".js", ".jsx", ".ts", ".tsx"],
                max_results=5,
            )
            for match in result.get("matches", []):
                fname = match["file"]
                if fname not in seen_files:
                    seen_files.add(fname)
                    read = filesystem_mcp_read(fname, repo_path)
                    if read.get("success"):
                        content_preview = read["content"][:2000]
                        context_blocks.append(
                            f"### {fname}\n```\n{content_preview}\n```"
                        )
                if len(context_blocks) >= 6:
                    break
            if len(context_blocks) >= 6:
                break

        if not context_blocks:
            return (
                f"Could not find relevant code for: '{question}'\n\n"
                "Suggestions:\n"
                "1. Run scan_repo() on this repository first\n"
                "2. Use search_code() with specific symbol names\n"
                "3. Try rephrasing with a function/class name from the codebase"
            )

        context = "\n\n".join(context_blocks)
        prompt = f"""You are a senior software architect helping a developer understand a codebase.

Question: {question}

Most relevant files found in the repository:

{context}

Answer the question clearly and specifically, referencing actual file names and code snippets.
If you are uncertain about something, say so clearly. Format your answer in markdown with headers."""

        response = _llm.generate_content(prompt)
        return response.text

    except Exception as e:
        return f"ERROR: ask_repo failed: {e}"


# ─────────────────────────────────────────────────────────────────────────────
#  TOOL 9 — analyze_pr
# ─────────────────────────────────────────────────────────────────────────────
@mcp.tool()
async def analyze_pr(owner: str, repo: str, pr_number: int, repo_path: str) -> str:
    """
    Analyze the blast radius of a GitHub Pull Request.
    This fetches the changed files from GitHub and runs impact analysis on them
    against the local repository clone.

    Args:
        owner: GitHub repository owner (e.g., 'shlokapol2005')
        repo: GitHub repository name (e.g., 'SoilSense')
        pr_number: The PR number to analyze (e.g., 1)
        repo_path: Absolute local path to the cloned repository.

    Returns:
        A formatted markdown string detailing the impact of the PR.
    """
    github_token = os.getenv("GITHUB_TOKEN", "")
    if not github_token:
        return "ERROR: GITHUB_TOKEN is not set in the backend/.env file."

    try:
        changed_files = await get_pr_files(owner, repo, pr_number, github_token)
    except Exception as e:
        return f"ERROR: Could not fetch files for PR #{pr_number}: {e}"

    if not changed_files:
        return f"PR #{pr_number} contains no files or could not be found."

    source_exts = {".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"}
    source_files = [f for f in changed_files if Path(f).suffix.lower() in source_exts]
    
    if not source_files:
        return f"PR #{pr_number} changes {len(changed_files)} files, but none are source code files (e.g., READMEs, docs). No architectural impact."

    try:
        cache = get_or_build_graph(repo_path)
        G = cache["G"]
    except Exception as e:
        return f"ERROR: Failed to build or load graph for {repo_path}: {e}"

    report = [f"## PR #{pr_number} Impact Analysis"]
    report.append(f"Analyzing {len(source_files)} source files (out of {len(changed_files)} total files changed).\n")

    overall_risk = "Low"
    RISK_ORDER = ["Low", "Medium", "High", "Critical"]
    all_affected = set()
    all_routes = set()

    for fname in source_files[:15]:  # Cap at 15 to avoid massive responses
        impact = get_impact(G, fname)
        if "error" in impact:
            report.append(f"- **{fname}**: Not in dependency graph.")
            continue
            
        risk = impact.get("risk", "Low")
        count = impact.get("count", 0)
        routes = impact.get("affected_routes", [])
        
        all_affected.update(impact.get("affected_files", []))
        all_routes.update(routes)
        
        if RISK_ORDER.index(risk) > RISK_ORDER.index(overall_risk):
            overall_risk = risk
            
        report.append(f"- **{fname}**: {risk} risk ({count} files affected, {len(routes)} routes at risk)")

    report.append(f"\n### Total Blast Radius")
    report.append(f"**Overall Risk**: {overall_risk}")
    report.append(f"**Total Downstream Files Affected**: {len(all_affected)}")
    report.append(f"**Total API Routes at Risk**: {len(all_routes)}")

    if all_routes:
        report.append("\n**API Routes at Risk:**")
        for route in sorted(list(all_routes)):
            report.append(f"- `{route}`")

    return "\n".join(report)


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point — run with stdio transport
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
