# 🤖 Code Detective — Discord Bot Integration Plan

> **Goal:** Let any developer in a Discord server ask Code Detective questions about a repository directly from chat — no browser needed.

---

## The Big Picture

```
Developer types in Discord
        ↓
/repobot trace payment flow
        ↓
Discord sends an Interaction event (HTTP POST) to your server
        ↓
discord_bot.py receives it → calls your existing FastAPI endpoints
        ↓
FastAPI → LangGraph Agent → Gemini → Answer
        ↓
Bot replies in Discord with formatted embed
```

Everything you've already built (agents, graph, FAISS, MCP) stays **100% unchanged**. The bot is just a new client that talks to your existing API.

---

## Group 1 — Discord App Setup (One-Time, No Code)

> These are configuration steps you do once on Discord's developer portal. Zero code involved.

### 1.1 Create a Discord Application
- Go to `discord.com/developers/applications` → **New Application**
- Give it a name: **RepoBot** or **Code Detective**
- This gives you an **Application ID** and a **Public Key**

### 1.2 Create a Bot User
- Inside the app → **Bot** tab → **Add Bot**
- Copy the **Bot Token** (treat like a password, goes in `.env`)
- Enable **Message Content Intent** (needed to read messages that @mention the bot)

### 1.3 Register Slash Commands
- You'll register commands like `/repobot` with sub-commands:
  - `/repobot qa <question>` — Ask a question about the repo
  - `/repobot trace <feature>` — Trace a feature flow
  - `/repobot impact <file>` — Run impact analysis
  - `/repobot arch` — Get architecture diagram
  - `/repobot deadcode` — Find dead code
  - `/repobot onboard` — Generate onboarding guide
- Commands are registered via Discord's REST API (a one-time `POST` call your bot makes at startup)

### 1.4 Invite the Bot to Your Server
- Generate an OAuth2 URL in the portal with scopes: `bot` + `applications.commands`
- Required permissions: **Send Messages**, **Embed Links**, **Read Message History**
- Open the URL → select your test server → **Authorize**

**What you need from this group:** `BOT_TOKEN`, `APPLICATION_ID`, `PUBLIC_KEY` → all go in `.env`

---

## Group 2 — Bot Backend (`discord_bot/`) — New Python Module

> A new folder inside your project that contains the bot's logic. This is completely separate from your FastAPI backend.

```
code-Detective(p)/
├── backend/          ← your existing FastAPI (unchanged)
├── discord_bot/      ← NEW: the bot lives here
│   ├── main.py       ← bot entry point / event loop
│   ├── commands.py   ← slash command handlers
│   ├── api_client.py ← talks to your FastAPI endpoints
│   ├── formatter.py  ← turns API responses into Discord embeds
│   └── .env          ← BOT_TOKEN (or share backend/.env)
└── frontend/         ← unchanged
```

### 2.1 `main.py` — Bot Entry Point
**What it does:**
- Uses the `discord.py` library (Python's standard Discord library)
- Logs in using `BOT_TOKEN`
- Listens for events: slash command interactions, @mentions, message reactions
- Registers slash commands on startup via Discord's API
- Keeps the bot alive with an async event loop

**Library:** `discord.py` (version 2.x — has full slash command support via `app_commands`)

```python
# pseudo-code of what it does
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    await tree.sync()   # registers /repobot commands with Discord

client.run(BOT_TOKEN)
```

### 2.2 `commands.py` — Slash Command Handlers
**What it does:**
- Defines each slash command using `@tree.command()` decorators
- Receives the user's input (e.g. `question="where is auth handled?"`)
- Calls the corresponding function in `api_client.py`
- Passes the result to `formatter.py`
- Sends the formatted embed back to Discord

**One handler per command:**

| Command | Calls | FastAPI endpoint |
|---|---|---|
| `/repobot qa` | `api_client.ask_question()` | `POST /api/agents/qa` |
| `/repobot trace` | `api_client.trace_flow()` | `POST /api/agents/flow` |
| `/repobot impact` | `api_client.get_impact()` | `POST /api/agents/impact` |
| `/repobot arch` | `api_client.get_arch()` | `POST /api/agents/arch` |
| `/repobot deadcode` | `api_client.get_deadcode()` | `GET /api/agents/dead_code` |
| `/repobot onboard` | `api_client.get_onboarding()` | `POST /api/agents/onboard` |

**Important Discord behavior:** Discord requires you to reply within **3 seconds** or the interaction times out. Since your LLM calls take 5–15 seconds, every command must immediately call `interaction.response.defer()` which shows a "thinking..." spinner. Then you send the real answer with `interaction.followup.send()`.

### 2.3 `api_client.py` — Talks to Your FastAPI
**What it does:**
- Uses `httpx` (async HTTP client) to call your FastAPI endpoints
- Handles timeouts, connection errors, and non-200 responses
- Returns the parsed JSON response to `commands.py`

**Why `httpx` not `requests`?** `requests` is blocking — it would freeze the bot's async event loop. `httpx` has a native async interface (`async with httpx.AsyncClient()`).

```python
# pseudo-code
async def ask_question(repo_path: str, index_name: str, question: str) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://localhost:8000/api/agents/qa",
            json={"question": question, "repo_path": repo_path, "index_name": index_name}
        )
        return response.json()
```

**Session management problem:** Your FastAPI stores the active repo/index in a session or request. The bot needs to know *which repo* to query. Solution: store the last-scanned repo per Discord channel ID in a simple dict or SQLite.

### 2.4 `formatter.py` — Makes Responses Look Good
**What it does:**
- Takes the raw JSON from FastAPI and builds a Discord `Embed` object
- An Embed is Discord's rich message format: has a title, color, fields, footer

**Per response type:**

| Response | Embed design |
|---|---|
| Q&A answer | Title: "🔍 Answer", description: the answer text, footer: files referenced |
| Flow trace | Title: "🔄 Feature Flow", one field per step (file → function → action) |
| Impact analysis | Title: "💥 Impact Analysis", color = risk color (red/orange/yellow/green), list of affected files |
| Architecture | Title: "🏗️ Architecture", paste Mermaid as a code block (Discord renders it as monospace) |
| Dead code | Title: "🪦 Dead Code", bulleted list of unused files |
| Onboarding | Title: "📚 Onboarding Guide", each module as a separate field |

**Discord embed limits:** Max 4096 chars in description, max 25 fields, max 1024 chars per field. Your formatter must truncate gracefully.

---

## Group 3 — Repo State Management — Tracking "Which Repo?"

> The problem: your FastAPI backend is stateless per-request (mostly). The bot needs to know which repo a user is asking about. This group solves that.

### 3.1 The Problem
When a user types `/repobot qa where is JWT validated?`, the bot needs to know:
- What is the `repo_path`?
- What is the `index_name` (FAISS index)?

This info isn't in the slash command — the user already scanned a repo earlier.

### 3.2 Solution: Channel-Bound Repo State
Each Discord channel gets one "active repo." The flow:

```
User: /repobot load django__django
Bot: ✅ Loaded repo: django/django (cloned to /cloned-repos/django__django)

User: /repobot qa where is the ORM query engine?
Bot: looks up channel_id → finds repo_path + index_name → calls FastAPI → replies
```

**Where to store it:**
- **Start simple:** Python `dict` in memory: `{channel_id: {repo_path, index_name}}`
- **Better:** A tiny `state.json` file that persists across bot restarts
- **Even better (Phase 2):** SQLite with `aiosqlite`

### 3.3 New Command: `/repobot load <github_url>`
- Calls `POST /api/mcp/clone` with the GitHub URL
- Then calls `POST /api/scan/repo` to build the graph + FAISS index
- Stores `{channel_id → repo_path, index_name}` in the state dict
- This can take 30–120 seconds for large repos → use `defer()` immediately

---

## Group 4 — Running Everything Together — Process Management

> How to actually run both the FastAPI backend and the Discord bot at the same time.

### 4.1 Two Separate Processes
The bot and the FastAPI server are two separate Python programs:

```
Terminal 1:                     Terminal 2:
uvicorn main:app --port 8000    python discord_bot/main.py
```

The bot talks to FastAPI over `localhost:8000` (HTTP). They don't share memory — the bot is just another client.

### 4.2 For Development: Run Both at Once
Use a `Procfile` or `run_all.py` script that starts both:

```python
# run_all.py
import subprocess, sys

api = subprocess.Popen(["uvicorn", "main:app", "--port", "8000"], cwd="backend")
bot = subprocess.Popen(["python", "discord_bot/main.py"])

try:
    api.wait()
except KeyboardInterrupt:
    api.terminate()
    bot.terminate()
```

### 4.3 Environment Variables
Add to your existing `backend/.env` (or create `discord_bot/.env`):
```
BOT_TOKEN=your_discord_bot_token_here
APPLICATION_ID=your_application_id
PUBLIC_KEY=your_public_key
FASTAPI_BASE_URL=http://localhost:8000
```

---

## Group 5 — New Dependencies (Add to requirements.txt)

```
discord.py>=2.3.2       # Discord bot framework (slash commands, embeds, events)
httpx>=0.27.0           # Async HTTP client to call FastAPI
aiosqlite>=0.20.0       # Optional: persistent channel state storage (Phase 2)
```

`discord.py` already has `aiohttp` as a dependency for its internal HTTP calls to Discord's API.

---

## Group 6 — What the User Experience Actually Looks Like

### Example 1: Loading a Repo
```
Shloka: /repobot load https://github.com/django/django
RepoBot: ⏳ Cloning repo... (this may take a minute)
[30 seconds later]
RepoBot: ✅ Repo loaded: django/django
         📁 1,847 files scanned
         🔗 Graph built: 12,340 nodes
         🔍 Vector index ready
         This channel is now set to: django/django
```

### Example 2: Q&A
```
Shloka: /repobot qa where is the ORM query builder?
RepoBot: 🔍 Answer — django/django
         The ORM query builder lives in `django/db/models/sql/compiler.py`.
         The main class is `SQLCompiler` (line 43). It's called from
         `QuerySet._iterator()` in `django/db/models/query.py` via `compiler.execute_sql()`.

         📄 Files referenced: compiler.py, query.py, sql/__init__.py
```

### Example 3: Impact Analysis
```
Shloka: /repobot impact django/db/models/sql/compiler.py
RepoBot: 💥 Impact Analysis — django/db/models/sql/compiler.py
         ⚠️ Risk Level: CRITICAL
         23 files will be affected if this file changes:

         • django/db/models/query.py
         • django/db/backends/sqlite3/operations.py
         • django/db/backends/postgresql/operations.py
         • ... and 20 more
```

### Example 4: Feature Flow
```
Shloka: /repobot trace user login flow
RepoBot: 🔄 Feature Flow — "user login flow"

         Step 1 → django/contrib/auth/views.py
                  LoginView.post() — Receives POST /login/

         Step 2 → django/contrib/auth/__init__.py
                  authenticate() — Validates credentials

         Step 3 → django/contrib/auth/backends.py
                  ModelBackend.authenticate() — Queries User model

         Step 4 → django/contrib/auth/models.py
                  User.check_password() — bcrypt hash comparison
```

---

## Build Order (What to Build First)

| Phase | What | Why First |
|---|---|---|
| **Phase 1** | Discord app setup + BOT_TOKEN | Without this, nothing works |
| **Phase 2** | `main.py` bot skeleton (logs in, says "I'm alive") | Proves the connection works |
| **Phase 3** | `api_client.py` (just Q&A endpoint) | Proves bot → FastAPI works |
| **Phase 4** | `/repobot qa` command + basic text reply | First end-to-end test |
| **Phase 5** | `formatter.py` + rich embeds | Makes it look good |
| **Phase 6** | Remaining commands (trace, impact, arch, deadcode, onboard) | Full feature set |
| **Phase 7** | `/repobot load` + channel state | Full UX flow |
| **Phase 8** | Error handling, timeouts, rate limits | Production-ready |

---

## What You Do NOT Need to Change

| Existing File | Status |
|---|---|
| `backend/main.py` | ✅ Unchanged |
| `backend/utils/agents.py` | ✅ Unchanged |
| `backend/utils/graph_builder.py` | ✅ Unchanged |
| `backend/utils/vector_index.py` | ✅ Unchanged |
| `backend/utils/mcp_layer.py` | ✅ Unchanged |
| `backend/routers/*.py` | ✅ Unchanged |
| `frontend/` | ✅ Unchanged |

The Discord bot is **purely additive** — it's a new client for your existing system.

---

## Files to Create (Summary)

| File | Lines (estimated) | Purpose |
|---|---|---|
| `discord_bot/main.py` | ~60 | Bot startup, event loop, command registration |
| `discord_bot/commands.py` | ~150 | One handler per slash command |
| `discord_bot/api_client.py` | ~80 | Async HTTP calls to FastAPI |
| `discord_bot/formatter.py` | ~120 | JSON → Discord Embeds |
| `discord_bot/state.py` | ~40 | Channel → repo mapping |

**Total new code: ~450 lines.** Your existing 2000+ lines of backend code is untouched.
