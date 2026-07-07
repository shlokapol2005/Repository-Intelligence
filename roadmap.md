# Code Detective — What's Next 🚀

## 1. ✅ What You've Already Built

| Layer | Status |
|---|---|
| FastAPI backend (`/api/scan`, `/api/graph`, `/api/agents`, `/api/search`) | ✅ Done |
| AST parser (Python + JS/TS) | ✅ Done |
| Dependency graph builder (`networkx`) | ✅ Done |
| Impact analysis + Dead code detection | ✅ Done |
| Mermaid.js export | ✅ Done |
| React Flow frontend (interactive graph) | ✅ Done |
| Discord bot (scan, graph, impact queries) | ✅ Done |
| MCP Layer (GitHub clone, FS read/list, code search, terminal) | ✅ Done |

---

## 2. 🔮 True MCP Server (Model Context Protocol)

You already have an **internal MCP-style layer** (`/api/mcp/*`), but that's just HTTP REST.  
A **real MCP Server** means Claude Desktop / Cursor / any MCP-compatible client can plug in directly.

### What to build

Create `mcp_server/server.py` using the official `mcp` Python SDK:

```python
# pip install mcp
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("code-detective")

@server.list_tools()
async def list_tools():
    return [
        Tool(name="scan_repo",    description="Scan a GitHub repo and parse all files"),
        Tool(name="impact",       description="Find what breaks if a file changes"),
        Tool(name="dead_code",    description="List unused files in a repo"),
        Tool(name="explain_file", description="AI explanation of any file in the repo"),
        Tool(name="search_code",  description="Semantic search across the codebase"),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "impact":
        # call your existing FastAPI endpoints or directly call utils
        ...
    return [TextContent(type="text", text=result)]

if __name__ == "__main__":
    import asyncio
    asyncio.run(stdio_server(server))
```

Register it in Claude Desktop's `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "code-detective": {
      "command": "python",
      "args": ["mcp_server/server.py"],
      "cwd": "/path/to/code-Detective(p)"
    }
  }
}
```

Now Claude can **natively call your tools** from inside the chat window.

---

## 3. 🎨 Graph Beautification (NetworkX → Visual Upgrade)

Your current graph uses React Flow on the frontend. Here are **layered improvements**:

### A. Layout Algorithms (biggest win)
| Algorithm | Use case | Library |
|---|---|---|
| `dagre` (current default) | General DAG | `@dagrejs/dagre` |
| **ELK hierarchical** | Large repos (100+ nodes) | `elkjs` |
| **Force-directed** | Cluster discovery | `d3-force` inside React Flow |
| **Radial/Circular** | Entrypoint-centered view | Custom position math |

```bash
npm install elkjs @xyflow/react
```

### B. Node Visual Layers
```js
// Color by language
const LANG_COLORS = {
  python:     "#3b82f6",   // blue
  javascript: "#f59e0b",   // amber
  typescript: "#06b6d4",   // cyan
  css:        "#8b5cf6",   // purple
  unknown:    "#6b7280",   // gray
};

// Size by in-degree (hub nodes are bigger)
const nodeSize = Math.max(60, 40 + node.data.in_degree * 8);
```

### C. Edge Types
- 🔴 **Critical path** edges (path between entrypoint and most used module)
- 🟡 **Cross-layer** edges (frontend → backend import, if detected)
- ✨ **Animated dashes** on circular dependency edges

### D. Minimap Clusters
Use React Flow's `<MiniMap>` with `nodeColor` callback to show language heatmap

### E. NetworkX-side Enrichment (before sending to frontend)
```python
import networkx as nx

# PageRank — which files are most "important"
pageranks = nx.pagerank(G)
G.nodes[node]["pagerank"] = pageranks[node]

# Betweenness centrality — which files are "bridges"
centrality = nx.betweenness_centrality(G)
G.nodes[node]["centrality"] = centrality[node]

# Strongly connected components → circular deps
sccs = list(nx.strongly_connected_components(G))
```

---

## 4. 🤯 Crazy Unique Automation Ideas

These go way beyond what anyone else is shipping:

### 🔥 #1 — "Git Blame Intelligence" (Most Unique)
> **Auto-detect who owns each file and auto-assign reviewers on PRs**

When a file changes, your system:
1. Parses `git log --follow <file>` → finds who wrote most of each file
2. Does impact analysis → finds downstream files
3. Automatically posts to GitHub PR: *"Warning: changing `auth.py` affects 12 files. Top expert: @john (wrote 73% of this file)"*

```python
# Webhook listener → auto PR comment with impact + ownership
```

### 🧠 #2 — "Codebase Drift Detector" (Automation)
> **Runs nightly. Compares your graph today vs 7 days ago. Sends Slack/Discord alert on architectural drift.**

- New circular dependencies added? → ALERT
- Dead code count increased by >5? → ALERT
- A core file (high betweenness) got too many new dependents? → ALERT

This is like a **codebase heartbeat monitor**.

### 🤖 #3 — "Auto-Refactor Agent" (AI Automation)
> **Detects highly coupled files → proposes and creates a PR with a refactored version**

1. Find files with centrality > 0.8 (everyone depends on them)
2. Send file content + dependency context to LLM
3. LLM proposes splitting into 2 smaller modules
4. Agent creates a GitHub PR with the proposed refactor
5. You review and merge

### 🌐 #4 — "Live Code Map" (Realtime)
> **WebSocket-powered graph that updates in real-time as your team pushes code**

- GitHub webhook → repo re-scanned on every push
- Frontend graph animates the diff (new edges glow green, removed edges fade red)
- Your team watches the architecture evolve live

### 🕵️ #5 — "Security Surface Analyzer" (Most Impressive for Portfolio)
> **Automatically finds your attack surface — which API routes reach which DB calls**

1. Trace path from each API route node → through the graph → to any file containing `db.query`, `execute(`, `Model.find(`
2. Highlight the full call chain as a "danger path"
3. Flag routes with no auth middleware in the chain

---

## 5. 📋 Recommended Priority Order

```
Week 1:  MCP Server (stdio) — plugs into Claude Desktop
Week 2:  Graph beautification (ELK layout + PageRank node sizing)
Week 3:  Git Blame Intelligence automation
Week 4:  Codebase Drift Detector (scheduled nightly scan)
```

> [!TIP]
> The MCP server is the **highest leverage item** right now — it turns Code Detective into a tool that AI assistants can invoke, which is a huge differentiator for your portfolio.

> [!NOTE]
> The Security Surface Analyzer is the most **impressive demo** — great for showing in interviews or pitching to startups.
