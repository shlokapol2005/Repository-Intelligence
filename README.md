<div align="center">

# 🔍 RepoLens

### Whole-repo structural intelligence for your codebase.

Point it at any GitHub repo and instantly get a **dependency graph**, **change-impact / blast-radius analysis**, an **architecture diagram**, **dead-code detection**, and **AI Q&A** — in your browser, in Discord, or right inside your Pull Requests.

<br/>

[![Open Web App](https://img.shields.io/badge/Open-Web_App-000000?logo=vercel&logoColor=white&style=for-the-badge)](https://repo-lens-gold.vercel.app/)
[![Add to Discord](https://img.shields.io/badge/Add_to-Discord-5865F2?logo=discord&logoColor=white&style=for-the-badge)](https://discord.com/oauth2/authorize?client_id=1521116372896055318&permissions=116736&integration_type=0&scope=bot+applications.commands)
[![Install GitHub App](https://img.shields.io/badge/Install-GitHub_App-181717?logo=github&logoColor=white&style=for-the-badge)](https://github.com/apps/repolens-impact-bot)

</div>

---

## Why RepoLens ?

Coding assistants like Cursor and Claude read files one at a time. They **don't** reason about your repo's *whole structure* — so they miss "what else breaks if I change this file?"

RepoLens builds a **dependency graph of your entire repository** and answers the structural questions those tools can't:

- 💥 **Blast radius** — "If I change `auth.py`, what files and API routes are affected?"
- 🏗️ **Architecture at a glance** — an auto-generated, clustered diagram of how your codebase fits together.
- 🪦 **Dead code** — files nothing imports.
- 🔗 **Class inheritance & imports** — cross-file relationships, not just single-file parsing.

Supports **Python, JavaScript, and TypeScript** (`.py`, `.js`, `.jsx`, `.ts`, `.tsx`).

---

## Three ways to use it

### 🌐 Web App — [repo-lens-gold.vercel.app](https://repo-lens-gold.vercel.app/)
Paste a GitHub URL and explore an **interactive dependency graph**, run impact analysis, view the architecture, and ask questions — all in the browser. Nothing to install.

### 🤖 Discord Bot — [Add to your server](https://discord.com/oauth2/authorize?client_id=1521116372896055318&permissions=116736&integration_type=0&scope=bot+applications.commands)
Bring repo intelligence into your team's engineering discussions. Invite the bot, then in any channel:

```
/repobot load https://github.com/your/repo
```

| Command | What it does |
|---|---|
| `/repobot load <github_url>` | Clone + scan a repo for this channel |
| `/repobot qa <question>` | Ask a natural-language question about the code |
| `/repobot trace <feature>` | Trace the code flow for a feature |
| `/repobot impact <file>` | Show what breaks if a file changes |
| `/repobot arch` | Generate an architecture diagram (as an image) |
| `/repobot deadcode` | Find unused files |
| `/repobot onboard` | Generate an onboarding guide |
| `/repobot status` | Show the repo loaded in this channel |

> No cloning or setup for you — just invite the bot and give it a GitHub URL. The backend does the rest.

### 🔧 GitHub App — [Install RepoLens Impact Bot](https://github.com/apps/repolens-impact-bot)
Install it on any repo and **every Pull Request automatically gets an impact-analysis comment** — blast radius, affected API routes, and a risk level. Zero configuration: no webhook, no token, no setup on your end.

The graph also **auto-updates on every push**, so the analysis always reflects your current code.

---

## Features

- **Dependency graph** — files as nodes, imports as edges (`networkx`), rendered interactively with React Flow.
- **Impact / blast-radius analysis** — transitive reverse-dependency walk + affected API routes + a Low→Critical risk score.
- **Architecture diagrams** — deterministic, clustered Mermaid, rendered to a clean PNG (no overlaps).
- **Dead-code detection** — files with zero importers (entrypoints & route files excluded).
- **AST parsing** — Python via `ast`, JS/TS via `tree-sitter`, extracting functions, classes, imports, exports, API routes, and class inheritance.
- **Semantic Q&A** — hybrid FAISS + keyword retrieval, answered by Gemini.
- **PR impact bot** — automatic, comment-based analysis on every PR (via the GitHub App).

---

## How it works

```
GitHub repo ──▶ clone ──▶ parse (ast / tree-sitter) ──▶ dependency graph (networkx)
                                                              │
                          ┌───────────────┬──────────────────┼───────────────┐
                          ▼               ▼                  ▼               ▼
                   impact analysis   architecture      dead code      semantic Q&A
                     (blast radius)   (Mermaid→PNG)    (zero in-deg)   (FAISS+Gemini)
                          │               │                  │               │
                          └───────────────┴──────────────────┴───────────────┘
                                                │
                        Web App  ·  Discord bot  ·  GitHub App  ·  MCP server
```

A single **FastAPI** backend hosts the intelligence engine; every surface (web, Discord, GitHub App, MCP) is a thin adapter over it.

---

## Tech stack

| Layer | Tech |
|---|---|
| Backend | FastAPI, networkx, tree-sitter, FAISS, Google Gemini |
| Frontend | React + Vite, React Flow, Mermaid |
| Surfaces | discord.py bot, GitHub App (webhook), MCP server (stdio) |
| Deploy | Render (backend + bot), Vercel (frontend) |

---

## Self-hosting / development

This repo contains the full stack. To run it yourself:

```bash
git clone https://github.com/shlokapol2005/Repository-Intelligence
cd Repository-Intelligence

# Backend + Discord bot
pip install -r backend/requirements.txt
# set backend/.env (GEMINI_API_KEY, DISCORD_BOT_TOKEN, GITHUB_WEBHOOK_SECRET, ...)
bash start.sh

# Frontend
cd frontend && npm install && npm run dev
```

- **GitHub App setup:** see [`backend/GITHUB_APP_SETUP.md`](backend/GITHUB_APP_SETUP.md)
- **MCP server (Claude Desktop / Cursor):** see [`mcp_server/README.md`](mcp_server/README.md)

---

<div align="center">

Built with 🔍 by [@shlokapol2005](https://github.com/shlokapol2005)

</div>
