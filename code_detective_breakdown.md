# 🔍 Code Detective — Complete Architecture & Market Breakdown

---

## 1. Problem Statement

Modern software teams work with codebases that have grown beyond what any single human can fully hold in their head. A typical production repository has:

- **50,000–500,000+ lines of code** spread across hundreds of files
- **Deep dependency chains** where a single utility function change can cascade into 40+ broken modules
- **Zero onboarding tooling** — new engineers spend 3–6 weeks just *reading* before they can contribute
- **No semantic search** — `grep` finds the string, not the *meaning*
- **No impact intelligence** — git blame tells you *who* touched it, not *what breaks if you change it*

**Existing solutions are either too shallow (GitHub code search) or too expensive/complex (enterprise tools like Sourcegraph, Snyk, or CodeClimate).** There is no tool that combines graph intelligence + LLM reasoning + visual exploration in a single open, installable tool.

> **Code Detective** solves this by treating a codebase as a *knowledge graph + semantic document store + agentic reasoning system*, not just a folder of text files.

---

## 2. How It's Different from Competitors

| Feature | Code Detective | GitHub Copilot | Sourcegraph | CodeScene | Snyk |
|---|---|---|---|---|---|
| AST-based dependency graph | ✅ Full DiGraph | ❌ None | ✅ Partial | ✅ Partial | ❌ None |
| Semantic vector search | ✅ FAISS + Gemini | ✅ Inline only | ✅ Enterprise | ❌ | ❌ |
| Multi-step LLM agents | ✅ LangGraph | ❌ Single shot | ❌ | ❌ | ❌ |
| Feature flow tracer | ✅ Graph + LLM | ❌ | ❌ | ❌ | ❌ |
| Impact analysis (cascade) | ✅ Graph traversal | ❌ | ❌ | ✅ | ✅ Vuln only |
| Dead code detection | ✅ In-degree=0 | ❌ | ❌ | ✅ | ❌ |
| Onboarding guide generator | ✅ Agent-generated | ❌ | ❌ | ❌ | ❌ |
| Self-hosted / local | ✅ Fully | ❌ Cloud-only | ❌ Cloud-only | ❌ | ❌ Cloud |
| Cost | Free (Gemini API) | $10–19/month | $49+/user/month | $$$$ | $$$$ |
| Supports cloning GitHub URLs | ✅ GitPython | ❌ | ✅ | ✅ | ✅ |

**Key Differentiator:** Code Detective is the only tool that chains `AST parsing → Dependency Graph → FAISS vector search → LangGraph multi-step agents` into one unified pipeline that runs **100% locally** using the Gemini API.

---

## 3. Market Analysis & CAGR

### Target Market

**Primary:** Developer tooling / DevOps intelligence market

| Segment | 2024 Market Size | 2030 Projected | CAGR |
|---|---|---|---|
| AI Code Assistants | $4.2B | $37.1B | ~43% |
| Static Analysis / SAST | $1.3B | $3.8B | ~19.6% |
| Developer Experience Platforms | $8.7B | $28.4B | ~21.8% |
| Application Security Testing | $6.1B | $18.9B | ~20.7% |
| Code Intelligence (semantic search) | $0.9B | $6.2B | ~37.8% |

> The combined addressable market for AI-native developer tooling is **$47B+ by 2030**, growing at a blended CAGR of ~38%.

### Who Buys This?

1. **Engineering Managers** — need impact analysis before deploying large PRs
2. **Senior Engineers** — onboarding new hires faster, understanding unfamiliar repos
3. **Security Teams** — finding what code paths are exposed to a vulnerable module
4. **Open Source Contributors** — understanding massive repos (Linux kernel, Django, React) before contributing

---

## 4. Full System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND                             │
│  React 19 + Vite 8 (Port 5173)                              │
│  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌───────────────┐  │
│  │ Repo    │ │ Graph    │ │  Q&A      │ │  Flow Tracer  │  │
│  │ Setup   │ │ Explorer │ │ Interface │ │  / Impact     │  │
│  └────┬────┘ └────┬─────┘ └─────┬─────┘ └───────┬───────┘  │
│       └───────────┴─────────────┴───────────────┘           │
│                      axios (HTTP)                            │
└─────────────────────────┬───────────────────────────────────┘
                           │ REST JSON
┌─────────────────────────▼───────────────────────────────────┐
│                    FASTAPI BACKEND (Port 8000)               │
│                                                              │
│  /api/scan    /api/graph   /api/search   /api/agents   /api/mcp
│       │            │            │              │            │
│  ┌────▼────┐  ┌────▼────┐ ┌────▼────┐ ┌──────▼────┐ ┌────▼────┐
│  │ Scanner │  │ Graph   │ │ Vector  │ │LangGraph  │ │  MCP    │
│  │ Router  │  │ Router  │ │ Router  │ │  Router   │ │ Router  │
│  └────┬────┘  └────┬────┘ └────┬────┘ └──────┬────┘ └────┬────┘
│       │            │            │              │            │
│  ┌────▼────────────▼────────────▼──────────────▼────────────▼────┐
│  │                    UTILS LAYER                                  │
│  │  scanner.py  parser.py  graph_builder.py  vector_index.py      │
│  │  mcp_layer.py           agents.py                              │
│  └────────────────────────┬────────────────────────────────────────┘
│                            │
│  ┌─────────────────────────▼──────────────────────────┐
│  │                  STORAGE LAYER                      │
│  │  /data/faiss_index/*.faiss  (vector store)          │
│  │  /data/faiss_index/*_meta.json (chunk metadata)     │
│  │  /cloned-repos/<repo_slug>/  (git clones)           │
│  └────────────────────────────────────────────────────┘
└──────────────────────────────────────────────────────────────┘
                           │
                    Gemini API (Cloud)
                    ├─ gemini-2.5-flash (LLM generation)
                    └─ gemini-embedding-001 (embeddings)
```

---

## 5. Backend Deep Dive — Every File, Why It Exists

### `main.py` — FastAPI Entry Point

**What it does:** Bootstraps the entire server. Registers all 5 routers. Configures CORS.

**Why FastAPI?**
- Async-first: handles concurrent LLM + file I/O efficiently without threading complexity
- Auto-generates OpenAPI docs at `/docs` for free
- Pydantic v2 data validation baked in — type-safe payloads between frontend and backend
- 2–4x faster than Flask for I/O-bound workloads (our primary workload is file reads + API calls)

**Critical patch in `main.py` (lines 7–18):** LangGraph 0.2.x internally imports `langchain.debug`, but we only install `langchain-core` to keep the dependency tree lean. This patch injects a minimal stub module to prevent `AttributeError` at startup — a real-world compatibility fix for production use.

```python
if "langchain" not in sys.modules:
    _lc_stub = types.ModuleType("langchain")
    _lc_stub.debug = False
    sys.modules["langchain"] = _lc_stub
```

---

### `utils/scanner.py` — Repository Scanner

**What it does:** The *ingestion entry point*. Walks a directory tree recursively and returns structured file metadata for every code file.

**Key decisions:**

| Decision | Rationale |
|---|---|
| `pathspec` library | Parses `.gitignore` files using the exact same `gitwildmatch` standard git uses — 100% accurate exclusion |
| `SKIP_DIRS` hardcoded set | Prevents scanning `node_modules`, `__pycache__`, `.venv` etc. — these have millions of lines of irrelevant code |
| Supported extensions hardcoded | Avoids binary files, compiled artifacts, and unknown formats that would crash the parser |
| Returns metadata only | Doesn't return content here — content is read lazily only when needed by parsers and agents |

**Why not use `git ls-files`?** Because the repo may not be a git repo. A user could point it at any local folder, not just a cloned git repo.

---

### `utils/parser.py` — AST Parser

**What it does:** Takes raw file content and returns structured metadata: imports, classes, functions, API routes.

**Two completely different parsing strategies:**

#### Python Files → stdlib `ast` module
```python
tree = ast.parse(content, filename=file_path)
for node in ast.walk(tree):
    # Handles: Import, ImportFrom, ClassDef, FunctionDef, AsyncFunctionDef
```
**Why `ast`?** Python's stdlib `ast` module is a full parse tree — it understands syntax at a structural level. It correctly handles nested classes, decorators, async functions, and complex import patterns like `from routers import scan`. This is far more reliable than regex for Python.

**What it extracts:**
- All `import` and `from X import Y` statements (with level for relative imports like `from . import foo`)
- All class definitions with their method lists
- All top-level and nested function definitions with parameters and line numbers
- **FastAPI/Flask/Django route decorators** — it looks for `@app.get("/path")`, `@router.post(...)` patterns and extracts the HTTP method + URL path

#### JavaScript/TypeScript Files → Regex-based
```python
_JS_IMPORT_RE = re.compile(r"""(?:import...|require(...))""", re.MULTILINE)
_EXPRESS_ROUTE_RE = re.compile(r"""(?:router|app)\.(get|post|...)...""")
```
**Why regex, not a full JS parser?** Building or bundling a JS parser in Python is heavyweight (Babel, Acorn, etc. are Node.js-only). Our use case is *structural extraction*, not full semantics — regex is sufficient for import graphs, function definitions, and Express routes.

**Why not tree-sitter?** Would require compiling language grammars and a C extension. Adds complexity for marginal gain in our current scope.

---

### `utils/graph_builder.py` — Dependency Graph Engine

**What it does:** Uses the parsed metadata to build a `networkx.DiGraph` where:
- **Nodes** = files (with language, functions, classes, API routes, size as attributes)
- **Edges** = import relationships (with `import_name` and `edge_type` as attributes)

**Why NetworkX?**
- Pure Python, no native compilation needed
- Rich algorithm library: `nx.descendants()`, `nx.ancestors()`, graph reversal, in-degree calculation
- Serializable to dict (used for JSON API responses) and Mermaid (used for visualizations)

**The import resolver (`_resolve_import`) — the most complex function in the entire codebase:**

This function takes a raw import string like `from utils.scanner import scan_repository` and resolves it to an actual node in the graph (e.g. `backend/utils/scanner.py`).

It handles **4 distinct resolution strategies**:

```
Strategy 1: JS relative imports     → "./auth", "../lib/utils"
Strategy 2: Python relative imports → from . import foo (level > 0)
Strategy 3: Package-style absolute  → from utils.scanner import ...
Strategy 4: Python root detection   → detects backend/ is sys.path root
```

**Python root detection:** It finds directories containing `main.py`, `app.py`, `manage.py` etc. and uses them as resolution roots. This is how `from utils.scanner import X` (which is relative to the `backend/` folder) gets correctly resolved to `backend/utils/scanner.py`.

**Graph algorithms used:**

| Algorithm | Where Used | What It Does |
|---|---|---|
| `nx.descendants(G.reverse())` | Impact Analysis | Finds all files that *transitively import* the changed file |
| `G.in_degree()` | Dead Code Detection | Files with in-degree=0 have nothing importing them → potentially unused |
| `G.subgraph(top_nodes)` | Mermaid generation | Limits diagram to top 40 most-connected nodes for readability |
| `G.successors(fpath)` | Flow expansion | Gets direct imports of a file (1-hop expansion) |
| `G.predecessors(fpath)` | Flow expansion | Gets files that import this file |

**Impact Risk Scoring:**
```python
if count == 0:   risk = "Low"
elif count <= 3: risk = "Medium"
elif count <= 10: risk = "High"
else:            risk = "Critical"
```

---

### `utils/vector_index.py` — FAISS Semantic Search Engine

**What it does:** Converts code files into vector embeddings and stores them in a local FAISS index. Enables natural language queries like *"where is JWT validated?"* to find relevant code chunks.

**Pipeline:**

```
File content
    ↓
_chunk_content() → 80-line chunks with 10-line overlap
    ↓
Gemini embedding API (models/gemini-embedding-001)
    task_type="retrieval_document"
    ↓
float32 numpy array
    ↓
faiss.normalize_L2()  → unit vectors for cosine similarity
    ↓
faiss.IndexFlatIP     → Inner Product index (≡ cosine on L2-normalized vectors)
    ↓
Saved to: /data/faiss_index/<name>.faiss
          /data/faiss_index/<name>_meta.json (chunk metadata with file + line numbers)
```

**Why FAISS?**
- Facebook AI's vector similarity library — industry standard, battle-tested
- `IndexFlatIP` does exact nearest-neighbor search (no approximation errors for moderate-sized repos)
- No server, no database, just flat files on disk — zero infrastructure overhead
- Handles millions of vectors efficiently

**Why not ChromaDB, Pinecone, or Weaviate?**
- ChromaDB/Qdrant: need a running server or docker container
- Pinecone: cloud-only, adds network latency and cost
- FAISS: pure library, runs in-process, instant startup, free

**Why Gemini embeddings and not OpenAI?**
- Gemini Embedding 001: 3072-dimensional embeddings, excellent code understanding
- Gemini API key already in use for LLM — single API credential, single billing
- Task type `retrieval_document` optimizes embeddings for asymmetric search (short query → long document)

**Chunking strategy:** 80 lines with 10-line overlap
- Overlap prevents missing context at chunk boundaries (a function spanning lines 78–95 would be split without overlap)
- 80 lines is roughly 2000–3000 tokens — fits comfortably in embedding model context

**Low-confidence guard (in agents.py):**
```python
CONFIDENCE_THRESHOLD = 0.45
if all(c.get("score", 0) < CONFIDENCE_THRESHOLD for c in sem_chunks):
    # Return "not found" message, do NOT call Gemini LLM
    # Prevents hallucination
```

---

### `utils/mcp_layer.py` — MCP Tool Abstraction

**What MCP is:** Model Context Protocol — a standardized way to define "tools" that LLM agents can call. Instead of the agent directly running code, it calls named tools with typed inputs/outputs.

**Four tools implemented:**

#### 1. `github_mcp_clone(github_url)`
Uses **GitPython** (`git.Repo.clone_from`) to:
- Parse the GitHub URL with regex
- Clone to `/cloned-repos/<org>__<repo>/` (depth=1 for speed — only latest commit)
- If already cloned: `git pull` to update
- Returns local path for the scanner to pick up

**Why GitPython?** Pure Python bindings to libgit2. No shell subprocess required. Cross-platform. Depth=1 (`--shallow`) massively speeds up cloning (10s vs 10 minutes for large repos).

#### 2. `filesystem_mcp_read(file_path, repo_root)`
Safe file reader with **directory traversal protection**:
```python
root = Path(repo_root).resolve()
target = (root / file_path).resolve()
if not str(target).startswith(str(root)):
    return {"success": False, "error": "Access outside repository root is not allowed."}
```
This prevents a malicious `file_path` like `../../../../etc/passwd` from escaping the repo boundary.

#### 3. `code_search_mcp(query, repo_root, extensions, max_results)`
Pure Python regex search across all files:
- Compiles query as regex (with case-insensitive flag by default)
- Skips `node_modules`, `__pycache__`, `.git`, `.venv` etc.
- Returns: file path, line number, 200-char snippet
- Hard cap at `max_results` with truncation flag

**Why custom regex search instead of ripgrep?** No subprocess dependency. No binary installation. Pure Python is sufficient for repos up to ~1M LOC at interactive speeds.

#### 4. `terminal_mcp_run(command, cwd)` *(Phase 2 stub)*
Runs whitelisted shell commands (`pytest`, `npm`, `git log`). Currently a placeholder for v2 — shows the security pattern: allowlist-based command gating.

---

### `utils/agents.py` — LangGraph Multi-Agent System

**What LangGraph is:** A library for building **stateful, multi-step agent workflows** as directed graphs. Each node in the graph is a Python function; state flows between them as a typed TypedDict.

**Why LangGraph over just calling Gemini directly?**
- Single LLM calls can't do: "search → read files → analyze → generate answer" in one shot
- LangGraph makes each step explicit, debuggable, and independently testable
- State accumulation: each node adds to `steps: list[str]` — gives the frontend a step-by-step audit trail of what the agent did
- Conditional edges: can branch based on confidence scores (e.g., skip file reading if search returned nothing)

---

#### Agent 1: Repository Q&A (`build_qa_agent`)

**Pipeline:** `retrieve → read_files → generate`

```
QAState:
  question, repo_path, index_name
  → retrieved_chunks, confidence_ok
  → file_contents
  → answer
```

**Step 1 — `_qa_retrieve`: Hybrid Search**

Two-pronged retrieval:
1. **Semantic search** via FAISS (understands meaning — finds "authentication" even if code says "JWT validation")
2. **Keyword search** via `code_search_mcp` using tokens extracted from the question
3. Merged deduplicated (semantic results take priority)
4. **Anti-hallucination guard**: if all similarity scores < 0.45, set `confidence_ok=False` and short-circuit

```python
keywords = _extract_keywords(question)  # No LLM — pure token extraction
# Avoids the model inventing terms not in the actual question
```

**Step 2 — `_qa_read_files`**: Reads the actual file content (up to 3000 chars per file) for the top matched files.

**Step 3 — `_qa_generate`**: Constructs a grounded prompt:
```
You are a senior software engineer reviewing a codebase.
Answer using ONLY the provided code context.
Be specific — reference file names, function names, and line patterns.
```

This **explicit grounding instruction** prevents Gemini from hallucinating about the codebase.

---

#### Agent 2: Architecture Diagram (`build_arch_agent`)

**Pipeline:** `to_mermaid → enhance`

- Step 1: Calls `build_dependency_graph()` → `generate_mermaid()` → raw Mermaid flowchart
- Step 2: Feeds raw diagram to Gemini with instruction to:
  - Group files into subgraphs (Frontend, Backend, Utils, API)
  - Use human-readable labels
  - Write a 3-sentence architecture summary
- Strips markdown fences from response with regex

---

#### Agent 3: Feature Flow Tracer (`build_flow_agent`)

**Pipeline:** `search → expand → trace`

This is the most sophisticated agent.

**Step 1 — `_flow_search`**: Finds files relevant to a feature using semantic search (preferred) or keyword fallback.

**Step 2 — `_flow_expand`**: **Graph-aware 1-hop expansion**
```python
# For each found file, add its direct importers AND importees
expanded.update(G.successors(fpath))   # what this file imports
expanded.update(G.predecessors(fpath)) # what imports this file
```
Also collects all directed edges within the expanded set and passes them as `graph_edges` to step 3. This gives Gemini the **actual dependency topology** rather than letting it guess from file names.

**Step 3 — `_flow_trace`**: Sends Gemini:
- Full file contents (up to 10,000 chars each)
- The verified dependency edges
- Strict rules: at least 4 steps, no invented file names, must include API entry point

Returns structured JSON:
```json
[
  {"step": 1, "file": "routers/scan.py", "function": "scan_repo", 
   "action": "Receives POST request and triggers scanner", "type": "api_route"},
  {"step": 2, ...}
]
```

---

#### Agent 4: Impact Analysis (`build_impact_agent`)

**Pipeline:** `traverse → explain`

- **Traverse**: `nx.descendants(G.reverse(), target_file)` — reverses all edges and finds descendants = all files that transitively depend on the target
- **Explain**: Sends impact data to Gemini for plain-English risk assessment

Risk levels: Low (0 affected) → Medium (1–3) → High (4–10) → Critical (11+)

---

#### Agent 5: Onboarding Guide (`build_onboard_agent`)

**Pipeline:** `analyze → generate`

- **Analyze**: Ranks nodes by `len(api_routes) * 3 + len(functions)` — API-heavy files are more "core" than utility files
- **Generate**: Creates a 4–6 module learning path with estimated time, key files, concepts, and exercises

---

## 6. Frontend Architecture

| File | Role |
|---|---|
| `App.jsx` | Root component, routing, tab navigation |
| `RepoSetup.jsx` | GitHub URL input + local path selector, triggers `/api/scan` |
| `GraphExplorer.jsx` | Interactive dependency graph (53KB — largest component) using `@xyflow/react` |
| `QAInterface.jsx` | Chat-style interface for repo Q&A agent |
| `FlowTracer.jsx` | Feature flow tracer with Mermaid diagram + step-by-step list |
| `ArchVisualizer.jsx` | Mermaid architecture diagram renderer |
| `ImpactDashboard.jsx` | Impact analysis UI with risk badge + affected file list |
| `DeadCode.jsx` | Dead code report with file list |
| `OnboardingMode.jsx` | Rendered markdown onboarding guide |

**Tech Stack Choices:**

| Library | Version | Why Chosen |
|---|---|---|
| React 19 | ^19.2.6 | Latest stable, concurrent features for smooth UI |
| Vite 8 | ^8.0.12 | Fastest dev server (ESM-native, HMR in <50ms) |
| `@xyflow/react` | ^12.11.0 | Best interactive graph/node visualization library for React (formerly ReactFlow) |
| `mermaid` | ^11.15.0 | Industry-standard diagram-from-text renderer; used for architecture + flow diagrams |
| `axios` | ^1.18.0 | HTTP client with better error handling than native fetch |
| `lucide-react` | ^1.18.0 | Clean, consistent icon set |
| `react-router-dom` | ^7.17.0 | SPA routing between the 8 views |

---

## 7. Data Flow — End to End

```
User inputs GitHub URL
        ↓
RepoSetup.jsx → POST /api/mcp/clone
        ↓
github_mcp_clone() → git.Repo.clone_from() (depth=1)
        ↓
Returns local_path
        ↓
POST /api/scan/repo
        ↓
scan_repository() → list of file metadata
parse_file() per file → AST metadata
        ↓
build_dependency_graph() → networkx DiGraph
build_vector_index() → FAISS index + metadata JSON
        ↓
        [Graph and index stored in memory / on disk]
        ↓
User asks a question in QAInterface
        ↓
POST /api/agents/qa  {"question": "...", "index_name": "...", "repo_path": "..."}
        ↓
build_qa_agent().invoke(state)
   → _qa_retrieve(): FAISS search + keyword search → merged chunks
   → _qa_read_files(): filesystem_mcp_read() per file
   → _qa_generate(): Gemini gemini-2.5-flash → answer text
        ↓
Response: {"answer": "...", "steps": [...], "retrieved_files": [...]}
        ↓
QAInterface.jsx renders formatted answer with step trace
```

---

## 8. Why Every Library Was Chosen

| Library | Why Not Alternatives |
|---|---|
| `fastapi` | Flask: no native async; Django: too heavy for a pure API |
| `uvicorn[standard]` | gunicorn: no async; uvicorn + websocket support for future streaming |
| `networkx` | igraph: C extension, harder install; custom graph: wheel reinvention |
| `faiss-cpu` | Pinecone: cloud-only + cost; ChromaDB: needs server; Weaviate: heavy |
| `google-generativeai` | OpenAI: separate billing; Anthropic: no free tier equivalent |
| `langgraph` | LangChain: monolithic, too opinionated; raw loops: no state management |
| `langchain-google-genai` | Required adapter between LangGraph and Gemini model interface |
| `gitpython` | subprocess git: fragile on Windows; pygit2: C extension required |
| `pathspec` | Manual gitignore parsing: incorrect edge cases; fnmatch: doesn't handle .gitignore syntax |
| `pydantic` v2 | v1: 2–4x slower validation; marshmallow: no FastAPI integration |
| `aiofiles` | For future async file reads in streaming endpoints |
| `httpx` | For future async HTTP calls in agents (replacing requests) |

---

## 9. Security Model

| Threat | Mitigation |
|---|---|
| Path traversal (file read) | `filesystem_mcp_read` checks `target.startswith(root)` |
| Arbitrary command execution | `terminal_mcp_run` allowlist: only `pytest`, `npm`, `git log`, etc. |
| Prompt injection | Agent prompts use f-strings with code context, not user-controlled instructions |
| Dependency confusion | All imports are resolved against actual file nodes in the graph — unresolvable imports are silently skipped |
| API key exposure | Loaded from `.env` via `python-dotenv`, never returned in API responses |

---

## 10. What's Currently Running vs. What's Planned

| Feature | Status |
|---|---|
| Repository scanner | ✅ Complete |
| AST parser (Python + JS/TS) | ✅ Complete |
| Dependency graph (NetworkX) | ✅ Complete |
| FAISS vector index | ✅ Complete |
| GitHub clone via MCP | ✅ Complete |
| Q&A Agent (LangGraph) | ✅ Complete |
| Architecture Diagram Agent | ✅ Complete |
| Feature Flow Tracer Agent | ✅ Complete |
| Impact Analysis Agent | ✅ Complete |
| Dead Code Detection | ✅ Complete |
| Onboarding Agent | ✅ Complete |
| Terminal MCP (run tests) | 🔄 Stub — Phase 2 |
| Streaming responses | 🔄 Planned |
| Multi-repo comparison | 🔄 Planned |
| Java / Go / Ruby support | 🔄 Scanner supports, parser is stub |
| Auth / user management | ❌ Not planned (local tool) |

