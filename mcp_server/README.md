# Code Detective — MCP Server

A true **Model Context Protocol (MCP)** server that exposes Code Detective's full intelligence engine to Claude Desktop, Cursor, and any MCP-compatible AI client.

## What it does

Instead of using the HTTP REST API, this MCP server communicates via **stdio** — it runs as a subprocess that any MCP client can spawn directly. No separate server process needed.

## Tools exposed

| Tool | Description |
|---|---|
| `clone_repo` | Clone a GitHub repository to local storage |
| `scan_repo` | Parse all files, extract AST symbols, build dependency graph |
| `build_graph` | Return the full dependency graph as JSON (nodes + edges) |
| `impact_analysis` | Find every file affected if a target file changes |
| `dead_code` | Detect files nobody imports (potential dead code) |
| `explain_file` | Gemini AI explanation of any file's purpose and architecture |
| `search_code` | Regex/symbol search across the entire codebase |
| `ask_repo` | Natural-language Q&A grounded in actual source code |

## Setup

### 1. Install the MCP SDK

```bash
cd backend
pip install "mcp[cli]>=1.0.0"
# or install all requirements:
pip install -r requirements.txt
```

### 2. Test the server directly

```bash
cd C:/Users/Shloka Pol/OneDrive/Desktop/code-Detective(p)
python mcp_server/server.py
```

You should see: `Starting Code Detective MCP server...` — it then waits for stdio input.

### 3. Register with Claude Desktop

Copy `claude_desktop_config.json` contents into your Claude Desktop config at:
```
%APPDATA%\Claude\claude_desktop_config.json
```

Or merge into your existing config:
```json
{
  "mcpServers": {
    "code-detective": {
      "command": "python",
      "args": ["mcp_server/server.py"],
      "cwd": "C:/Users/Shloka Pol/OneDrive/Desktop/code-Detective(p)"
    }
  }
}
```

Restart Claude Desktop — you'll see the 🔌 tools icon appear.

### 4. Use with MCP Inspector (debugging)

```bash
npx @modelcontextprotocol/inspector python mcp_server/server.py
```

## Example Claude prompts once connected

> "Clone https://github.com/fastapi/fastapi and tell me how routing works"

> "Scan C:/path/to/my/project and show me the dead code"

> "What happens if I change `backend/utils/auth.py` in my project?"

> "Explain what `src/middleware/rateLimit.ts` does"

> "Search for all TODO comments in the Python files"

## Architecture

```
mcp_server/server.py
    └── imports from backend/
        ├── utils/mcp_layer.py      (clone, read, search)
        ├── utils/graph_builder.py  (impact, dead code, graph)
        └── utils/agents.py         (graph cache, Gemini AI)
```

The MCP server reuses **all existing backend utilities** — zero code duplication.
