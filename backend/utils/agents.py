"""
AI Features — Agents & Pipelines

Agents (LangGraph — non-deterministic, multi-step):
  1. Repository Q&A
  3. Feature Flow Tracing

Pipelines (plain functions — deterministic, sequential):
  2. Architecture Diagram Generation
  4. Impact Analysis
  5. Onboarding Guide Generation
"""
import os
import re
from typing import TypedDict, Annotated
import operator

import google.generativeai as genai
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END

from utils.vector_index import semantic_search
from utils.mcp_layer import filesystem_mcp_read, code_search_mcp
from utils.graph_builder import get_impact, detect_dead_code, generate_mermaid

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

_llm = genai.GenerativeModel("gemini-2.5-flash")


def _gemini(prompt: str) -> str:
    """Call Gemini and return response text."""
    response = _llm.generate_content(prompt)
    return response.text


# ─────────────────────────────────────────────────────────────────────────────
#  1. REPOSITORY Q&A AGENT
# ─────────────────────────────────────────────────────────────────────────────

class QAState(TypedDict):
    question: str
    repo_path: str
    index_name: str
    retrieved_chunks: list[dict]
    file_contents: list[dict]
    answer: str
    confidence_ok: bool   # False when similarity scores are all too low
    steps: Annotated[list[str], operator.add]


# Stopwords to exclude from keyword extraction
_QA_STOP = {"what", "where", "when", "which", "who", "does", "this", "that",
             "have", "with", "from", "into", "about", "your", "their", "there",
             "here", "some", "then", "than", "more", "just", "been", "will"}


def _extract_keywords(text: str, min_len: int = 4) -> list[str]:
    """Extract meaningful technical tokens from natural language text.
    No LLM involved — just tokenises the text and filters stop-words.
    This is safe: it never invents terms not present in the question.
    """
    tokens = re.sub(r"[^a-z0-9_]", " ", text.lower()).split()
    return [t for t in tokens if len(t) >= min_len and t not in _QA_STOP]


def _qa_retrieve(state: QAState) -> QAState:
    """Step 1: Hybrid search — semantic (FAISS) + keyword fallback.

    Strategy:
    1. Run semantic search with the full question (understands meaning).
    2. Also run keyword search on tokens extracted from the question
       (catches exact identifiers like function/class names).
    3. Merge both result sets, deduplicated by file.
    4. Low-confidence guard: if ALL similarity scores < 0.45, flag it
       so _qa_generate returns a helpful "not found" message instead
       of hallucinating.
    """
    question   = state["question"]
    index_name = state["index_name"]
    repo_path  = state["repo_path"]

    # ── Semantic search ────────────────────────────────────────────────────────
    sem_chunks = semantic_search(question, index_name, top_k=8)

    # ── Low-confidence check ───────────────────────────────────────────────────
    CONFIDENCE_THRESHOLD = 0.45
    if sem_chunks and all(c.get("score", 0) < CONFIDENCE_THRESHOLD for c in sem_chunks):
        return {
            **state,
            "retrieved_chunks": [],
            "confidence_ok": False,
            "steps": ["⚠️ Semantic search returned low-confidence results — no close matches found."],
        }

    # ── Keyword search on tokens extracted from the question (no LLM) ──────────
    keywords = _extract_keywords(question)
    kw_files: set[str] = set()
    kw_chunks: list[dict] = []
    for kw in keywords[:6]:  # try up to 6 keywords
        kw_results = code_search_mcp(
            query=kw,
            repo_root=repo_path,
            extensions=[".py", ".js", ".jsx", ".ts", ".tsx"],
            max_results=5,
        )
        for m in kw_results.get("matches", []):
            if m["file"] not in kw_files:
                kw_files.add(m["file"])
                kw_chunks.append({"file": m["file"], "text": m["snippet"],
                                   "start_line": m["line"], "score": 0.5})

    # ── Merge: semantic results first, then keyword-only additions ─────────────
    sem_files = {c["file"] for c in sem_chunks}
    merged = list(sem_chunks) + [c for c in kw_chunks if c["file"] not in sem_files]

    return {
        **state,
        "retrieved_chunks": merged[:10],
        "confidence_ok": True,
        "steps": [f"🔍 Hybrid search: {len(sem_chunks)} semantic + {len(kw_chunks)} keyword chunks merged ({len(merged)} unique files)."],
    }


def _qa_read_files(state: QAState) -> QAState:
    """Step 2: Skip file reading if confidence is too low."""
    if not state.get("confidence_ok", True):
        return {**state, "file_contents": [], "steps": ["⏭️ Skipped file reading (low confidence)."]}

    seen = set()
    file_contents = []
    for chunk in state["retrieved_chunks"]:
        fpath = chunk.get("file", "")
        if fpath and fpath not in seen:
            seen.add(fpath)
            result = filesystem_mcp_read(fpath, state["repo_path"])
            if result.get("success"):
                file_contents.append({
                    "file": fpath,
                    "content": result["content"][:3000],
                })
    return {**state, "file_contents": file_contents, "steps": [f"📂 Read {len(file_contents)} relevant files."]}


def _qa_generate(state: QAState) -> QAState:
    """Step 3: Answer using Gemini, or return a clear 'not found' message."""
    # Low-confidence early exit — no hallucination
    if not state.get("confidence_ok", True) or not state["file_contents"]:
        answer = (
            f"⚠️ I couldn't find relevant code in this repository for your question:\n\n"
            f"**\"{state['question']}\"**\n\n"
            "**Possible reasons:**\n"
            "- The repository may not have been scanned/indexed yet (use the Scan tab first).\n"
            "- The feature you're asking about may not exist in this codebase.\n"
            "- Try rephrasing with a specific function name, class name, or file name."
        )
        return {**state, "answer": answer, "steps": ["⚠️ Returned low-confidence fallback message."]}

    context_parts = []
    for fc in state["file_contents"]:
        context_parts.append(f"### File: {fc['file']}\n```\n{fc['content']}\n```")

    context = "\n\n".join(context_parts)
    prompt = f"""You are a senior software engineer reviewing a codebase.
Answer the following question using ONLY the provided code context.
Be specific — reference file names, function names, and line patterns.
If the answer cannot be found in the code context, say so explicitly.
Format your answer with clear sections and code snippets where helpful.

QUESTION: {state['question']}

CODE CONTEXT:
{context}

Answer:"""

    answer = _gemini(prompt)
    return {**state, "answer": answer, "steps": ["🤖 Generated answer using Gemini."]}


# ── Compiled agent singletons ── built once, reused per process ────────────────────
_qa_agent_instance = None


def build_qa_agent():
    """Return the singleton compiled QA agent (built once per process)."""
    global _qa_agent_instance
    if _qa_agent_instance is None:
        g = StateGraph(QAState)
        g.add_node("retrieve", _qa_retrieve)
        g.add_node("read_files", _qa_read_files)
        g.add_node("generate", _qa_generate)
        g.set_entry_point("retrieve")
        g.add_edge("retrieve", "read_files")
        g.add_edge("read_files", "generate")
        g.add_edge("generate", END)
        _qa_agent_instance = g.compile()
    return _qa_agent_instance


# ─────────────────────────────────────────────────────────────────────────────
#  2. ARCHITECTURE DIAGRAM — Pipeline (no agent)
# ─────────────────────────────────────────────────────────────────────────────

def generate_architecture(repo_path: str) -> dict:
    """Generate an architecture diagram + AI summary for a repo.

    The Mermaid diagram is produced **deterministically** by generate_mermaid
    (clustered, styled, valid) rather than by the LLM — this is what gets
    rendered to a PNG for Discord/Slack, so it must always be syntactically
    valid. The LLM is used only for the prose summary, grounded in real graph
    facts, and any LLM failure degrades to a factual fallback summary rather
    than breaking the diagram.

    Returns:
        {"mermaid": str, "summary": str, "steps": list[str]}
    """
    from utils.graph_builder import build_dependency_graph, generate_mermaid, build_inheritance_edges
    from utils.mcp_layer import resolve_repo
    steps: list[str] = []

    # Step 0: Resolve identifier (path / GitHub URL / slug) → local clone.
    repo_path = resolve_repo(repo_path)

    # Step 1: Build graph → deterministic, render-safe Mermaid
    G = build_dependency_graph(repo_path)
    mermaid = generate_mermaid(G)
    steps.append("📊 Built dependency graph and clustered Mermaid diagram.")

    # Step 2: Gather concrete facts to ground the summary (no hallucinated structure)
    total_nodes = G.number_of_nodes()
    total_edges = G.number_of_edges()
    langs: dict[str, int] = {}
    api_files: list[str] = []
    for n, d in G.nodes(data=True):
        lang = d.get("language", "unknown")
        langs[lang] = langs.get(lang, 0) + 1
        if d.get("api_routes"):
            api_files.append(f"{n} ({len(d['api_routes'])} routes)")
    top_connected = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:8]
    inheritance = build_inheritance_edges(G)

    facts = (
        f"Files: {total_nodes}, Dependencies: {total_edges}\n"
        f"Languages: {langs}\n"
        f"API route files: {api_files[:10] or 'none detected'}\n"
        f"Most-connected files: {top_connected}\n"
        f"Class inheritance (child→parent): "
        f"{[(e['child_class'], e['parent_class']) for e in inheritance][:10] or 'none'}"
    )

    prompt = (
        "You are a software architect. Based ONLY on these facts about a "
        "codebase's dependency graph, write a concise 3-4 sentence architecture "
        "summary: what the main layers/modules are, how they connect, and where "
        "the structural hotspots (most-connected files) are. Do not invent files "
        "or details not implied by the facts.\n\n"
        f"{facts}"
    )

    # Step 3: LLM summary — grounded, and non-fatal if it fails.
    try:
        summary = _gemini(prompt).strip()
    except Exception:
        summary = ""

    if summary:
        steps.append("✨ Wrote AI architecture summary.")
    else:
        lang_str = ", ".join(f"{k}: {v}" for k, v in sorted(langs.items()))
        summary = (
            f"This repository has {total_nodes} source files and {total_edges} "
            f"import dependencies ({lang_str}). "
            f"{len(api_files)} file(s) expose API routes. "
            "(AI summary unavailable; showing graph-derived facts.)"
        )
        steps.append("⚠️ AI summary unavailable — showing graph-derived facts.")

    return {
        "mermaid": mermaid,
        "summary": summary,
        "steps": steps,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  3. FEATURE FLOW TRACER AGENT
# ─────────────────────────────────────────────────────────────────────────────

class FlowState(TypedDict):
    feature: str
    repo_path: str
    index_name: str
    search_results: list[dict]
    flow_trace: list[dict]
    steps_structured: list[dict]   # structured JSON steps for Mermaid rendering
    graph_edges: list[tuple]       # directed edges (src, dst) from dependency graph
    explanation: str
    disclaimer: str                # non-empty when no literal keyword match was found
    feature_exists: bool           # guard rail to prevent tracing non-existent features
    steps: Annotated[list[str], operator.add]


def _flow_search(state: FlowState) -> FlowState:
    """Step 1: Find files relevant to the feature using semantic search.

    Strategy:
      1. Try semantic/vector search (same engine as Q&A) — handles natural language well.
      2. If no index exists, fall back to keyword-based regex search using
         individual words extracted from the query.
    """
    feature = state["feature"]
    index_name = state.get("index_name", "")
    repo_path = state["repo_path"]

    # ── Strategy 1: Semantic search (preferred) ────────────────────────────────
    semantic_chunks = []
    if index_name:
        semantic_chunks = semantic_search(feature, index_name, top_k=10)

    if semantic_chunks:
        # Normalize to the same format expected by _flow_trace
        matches = [
            {
                "file": chunk["file"],
                "line": chunk.get("start_line", 1),
                "snippet": chunk.get("text", "")[:200],
            }
            for chunk in semantic_chunks
        ]

        # ── Literal keyword check ──────────────────────────────────────────────
        # Extract core words from the query (≥4 chars, skip filler words).
        _filler = {"trace", "show", "list", "find", "what", "flow", "does",
                   "the", "and", "for", "this", "with", "that", "from",
                   "into", "about", "any", "have", "there", "happening"}
        core_keywords = [
            w for w in re.sub(r"[^a-z0-9]", " ", feature.lower()).split()
            if len(w) >= 4 and w not in _filler
        ]

        # Build a single string of all matched content to search against.
        matched_content = " ".join(
            m.get("file", "").lower() + " " + m.get("snippet", "").lower()
            for m in matches
        )
        exact_hit = any(kw in matched_content for kw in core_keywords)

        disclaimer = (
            f"⚠️ No exact match for '{feature}' found in this repository. "
            f"The keywords {core_keywords} do not appear literally in the codebase. "
            f"Showing the closest semantic match — this may represent a conceptually similar "
            f"flow, not a direct implementation of '{feature}'."
            if (not exact_hit and core_keywords) else ""
        )

        return {
            **state,
            "search_results": matches,
            "flow_trace": [],
            "steps_structured": [],
            "graph_edges": [],
            "disclaimer": disclaimer,
            "steps": [f"🔍 Found {len(matches)} relevant code chunks via semantic search for '{feature}'."],
        }

    # ── Strategy 2: Keyword fallback ───────────────────────────────────────────
    # Extract meaningful words (≥4 chars, skip stop-words) and search each.
    stop_words = {"trace", "show", "list", "find", "what", "how", "does", "the",
                  "and", "for", "this", "with", "that", "from", "into", "about"}
    words = [w for w in re.sub(r"[^a-z0-9]", " ", feature.lower()).split()
             if len(w) >= 4 and w not in stop_words]

    all_matches: list[dict] = []
    seen_files: set[str] = set()

    for keyword in words[:5]:  # try up to 5 keywords
        results = code_search_mcp(
            query=keyword,
            repo_root=repo_path,
            extensions=[".py", ".js", ".jsx", ".ts", ".tsx"],
            max_results=10,
        )
        for m in results.get("matches", []):
            if m["file"] not in seen_files:
                seen_files.add(m["file"])
                all_matches.append(m)

    return {
        **state,
        "search_results": all_matches,
        "flow_trace": [],
        "steps_structured": [],
        "graph_edges": [],
        "steps": [
            f"🔎 Keyword search for {words[:5]} found {len(all_matches)} files "
            f"(no semantic index — scan the repo first for best results)."
            if words else
            f"🔎 Found {len(all_matches)} code references via keyword search."
        ],
    }


def _flow_validate(state: FlowState) -> FlowState:
    """Step 2: Validate if the feature actually exists in the search results.
    
    Uses only the retrieved snippets (very low token cost, no full files read yet)
    to ask the LLM if this is a false positive match. If it is, we exit early.
    """
    feature = state["feature"]
    search_results = state["search_results"]

    if not search_results:
        return {
            **state,
            "feature_exists": False,
            "explanation": f"⚠️ No files found matching '{feature}'.",
            "steps": ["🛡️ Validation check: No search results found. Exiting early."],
        }

    # Compile a small summary of snippets for the LLM to inspect
    snippets = []
    for r in search_results[:5]:
        snippets.append(f"File: {r['file']}\nSnippet: {r.get('snippet', '')}")
    snippets_text = "\n\n".join(snippets)

    prompt = f"""You are an AI codebase validator.
Analyze if the following feature is actually implemented or referenced in the codebase based on the top search results.
Feature to check: "{feature}"

Top search results:
{snippets_text}

Does this codebase actually contain any implementation, configuration, or references to "{feature}"?
Respond in the following JSON format:
{{
  "exists": true or false,
  "reason": "<one sentence explanation why it exists or why it is a false positive>"
}}
Return ONLY the JSON object. Do not include markdown formatting or any other text."""

    import json as _json
    try:
        raw_res = _gemini(prompt)
        clean = re.sub(r"^```[a-z]*\s*", "", raw_res.strip(), flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean).strip()
        res = _json.loads(clean)
        exists = res.get("exists", True)
        reason = res.get("reason", "")
    except Exception as e:
        # Fallback to True if validation fails to parse, so we don't break the agent
        exists = True
        reason = f"Validation check failed to parse ({e}). Proceeding anyway."

    explanation = ""
    if not exists:
        explanation = (
            f"⚠️ **Feature Not Found**\n\n"
            f"I analyzed the codebase but could not find any active implementation or references to **\"{feature}\"**.\n\n"
            f"*Reason:* {reason}"
        )

    return {
        **state,
        "feature_exists": exists,
        "explanation": explanation,
        "steps": [f"🛡️ Validation check: Feature exists = {exists} ({reason})."],
    }



def _flow_trace(state: FlowState) -> FlowState:
    """Step 3: Read matched files and ask Gemini to produce structured flow steps.

    Uses graph edges to give Gemini the actual dependency topology, so it can
    trace a real call chain instead of guessing from file contents alone.
    Strict rules force at least 4 steps when evidence exists.
    Falls back to plain text if JSON parsing fails.
    """
    seen_files: dict[str, str] = {}
    # Also keep the best matching snippet per file from search results
    snippet_by_file: dict[str, str] = {}
    for match in state["search_results"][:12]:
        fpath = match["file"]
        if fpath not in seen_files:
            result = filesystem_mcp_read(fpath, state["repo_path"])
            if result.get("success"):
                seen_files[fpath] = result["content"][:10000]
        # Keep the most relevant snippet for this file (from the vector search hit)
        if fpath not in snippet_by_file and match.get("snippet"):
            snippet_by_file[fpath] = match["snippet"]

    # Guard: empty context → helpful message, no hallucination
    if not seen_files:
        no_match_msg = (
            f"⚠️ No relevant files were found in this repository for: "
            f"\"{state['feature']}\".\n\n"
            "Please try:\n"
            "- A different search term (a function name or keyword that appears in the code)\n"
            "- Scanning and indexing the repository first via the Scan tab"
        )
        return {**state, "explanation": no_match_msg, "steps_structured": [],
                "steps": ["⚠️ No matching files found — skipped Gemini call."]}

    # ── Build dependency topology string from graph edges ──────────────────────
    # Only include edges where both endpoints are in our selected file set
    selected = set(seen_files.keys())
    graph_edges = state.get("graph_edges", [])
    relevant_edges = [(u, v) for u, v in graph_edges if u in selected and v in selected]

    if relevant_edges:
        edges_section = "DEPENDENCY GRAPH (true import edges — use these to order steps):\n"
        edges_section += "\n".join(f"  {u} -> {v}" for u, v in relevant_edges)
    else:
        edges_section = "DEPENDENCY GRAPH: Not available — infer order from import statements in the code."

    context = "\n\n".join([f"### {f}\n```\n{c}\n```" for f, c in seen_files.items()])
    available_files = list(seen_files.keys())

    prompt = f"""You are a software engineer tracing a feature through a codebase.
Feature to trace: "{state['feature']}"

{edges_section}

CRITICAL RULES — follow all of these:
1. Identify the entry point (API route, CLI entry, or main controller). Start there.
2. Follow actual function calls and imported services step by step.
3. Include any database interactions (queries, ORM calls) as their own step.
4. Include any external API calls (HTTP requests, third-party SDKs) as their own step.
5. End with the final output or response returned to the caller.
6. Produce AT LEAST 4 steps if there is enough evidence in the code context.
7. ONLY reference files from the "Available files" list below — never invent file names.

Available files: {available_files}

Code context:
{context}

Return a JSON array of steps. Each step must have these exact fields:
{{
  "step": <number>,
  "file": "<relative path from Available files list>",
  "function": "<function or class name, or empty string if none>",
  "action": "<one sentence: what happens at this step>",
  "type": "<one of: api_route | middleware | service | database | external | util>"
}}

Return ONLY the JSON array. No markdown fences, no explanation outside the array."""

    raw = _gemini(prompt)

    # Parse JSON — fallback to text mode if Gemini doesn't return valid JSON
    import json as _json
    steps_structured: list[dict] = []
    explanation = ""
    try:
        # Strip potential markdown fences
        clean = re.sub(r"^```[a-z]*\s*", "", raw.strip(), flags=re.IGNORECASE)
        clean = re.sub(r"\s*```$", "", clean).strip()
        steps_structured = _json.loads(clean)
        # Build human-readable explanation from structured steps
        lines = []
        for s in steps_structured:
            icon = {
                "api_route": "🌐", "middleware": "🔒", "service": "⚙️",
                "database": "🗄️", "external": "🔌", "util": "🔧",
            }.get(s.get("type", ""), "📌")
            fn = f" → `{s['function']}`" if s.get("function") else ""
            lines.append(f"{s['step']}. {icon} **{s['file']}**{fn}\n   {s['action']}")
        explanation = "\n\n".join(lines)
    except Exception:
        # JSON parsing failed — use raw text as explanation
        steps_structured = []
        explanation = raw

    return {
        **state,
        "explanation": explanation,
        "steps_structured": steps_structured,
        "steps": [f"🔗 Traced {len(steps_structured) or 'unknown number of'} steps using Gemini "
                  f"(graph edges: {len(relevant_edges)} used)."],
    }


def _flow_expand(state: FlowState) -> FlowState:
    """Step 1.5: Graph-aware multi-hop expansion + edge collection.

    Takes the files found by semantic/keyword search and expands the set
    by 1 hop through the actual import dependency graph. Also collects
    all directed edges (src -> dst) among the expanded file set and stores
    them in state['graph_edges'] so _flow_trace can pass the real
    dependency topology to Gemini instead of letting it guess from imports.
    """
    if not state["search_results"]:
        return {**state, "graph_edges": []}

    try:
        cache = get_or_build_graph(state["repo_path"])
        G = cache["G"]
    except Exception:
        # If graph can't be built, continue without expansion
        return {**state, "graph_edges": [],
                "steps": ["ℹ️ Dependency graph not available — skipped multi-hop expansion."]}

    found_files = {m["file"] for m in state["search_results"]}
    expanded: set[str] = set(found_files)

    # 1-hop: collect direct imports and importers of found files
    for fpath in list(found_files):
        if G.has_node(fpath):
            # Files this file imports (outgoing edges = dependencies)
            expanded.update(G.successors(fpath))
            # Files that import this file (incoming edges = dependents)
            expanded.update(G.predecessors(fpath))

    # ── Collect all directed edges whose both endpoints are in expanded set ─────
    # These form the verified dependency topology we'll pass to Gemini.
    graph_edges: list[tuple[str, str]] = []
    for fpath in expanded:
        if G.has_node(fpath):
            for dep in G.successors(fpath):
                if dep in expanded:
                    graph_edges.append((fpath, dep))

    new_files = expanded - found_files
    additional = [{"file": f, "line": 1, "snippet": ""} for f in list(new_files)[:12]]

    return {
        **state,
        "search_results": state["search_results"] + additional,
        "graph_edges": graph_edges,
        "steps": [
            f"🕸️ Graph expansion: added {len(new_files)} files, "
            f"collected {len(graph_edges)} dependency edges ({len(expanded)} total files)."
        ],
    }


# ── Compiled agent singletons ── built once, reused per process ────────────────────
_flow_agent_instance = None


def should_continue_flow(state: FlowState):
    """Routing function: stop the graph if the feature does not exist."""
    if state.get("feature_exists", True) is False:
        return "end"
    return "continue"


def build_flow_agent():
    """Return the singleton compiled Flow agent (built once per process)."""
    global _flow_agent_instance
    if _flow_agent_instance is None:
        g = StateGraph(FlowState)
        g.add_node("search", _flow_search)
        g.add_node("validate", _flow_validate)
        g.add_node("expand", _flow_expand)
        g.add_node("trace", _flow_trace)
        
        g.set_entry_point("search")
        g.add_edge("search", "validate")
        g.add_conditional_edges(
            "validate",
            should_continue_flow,
            {
                "continue": "expand",
                "end": END
            }
        )
        g.add_edge("expand", "trace")
        g.add_edge("trace", END)
        _flow_agent_instance = g.compile()
    return _flow_agent_instance


# ─────────────────────────────────────────────────────────────────────────────
#  4. IMPACT ANALYSIS — Pipeline (no agent)
# ─────────────────────────────────────────────────────────────────────────────

def run_impact_analysis(graph, target_file: str) -> dict:
    """Run impact analysis: graph traversal → Gemini risk summary.

    Pipeline:
        get_impact(nx.descendants) → Gemini risk explanation

    Returns:
        {"impact": dict, "risk_explanation": str, "steps": list[str]}
    """
    steps: list[str] = []

    # Step 1: Graph traversal
    impact = get_impact(graph, target_file)
    steps.append("📈 Ran graph traversal to find affected files.")

    # Step 2: Gemini explanation
    if "error" in impact:
        return {
            "impact": impact,
            "risk_explanation": impact["error"],
            "steps": steps + ["❌ File not found in graph."],
        }

    affected = "\n".join(impact.get("affected_files", [])[:20])
    routes = "\n".join([f"  {r['method']} {r['path']} ({r['file']})" for r in impact.get("affected_routes", [])[:10]])

    prompt = f"""A developer is about to modify: {impact['target']}

Impact Analysis:
- Risk Level: {impact['risk']}
- {impact['affected_count']} files will be affected
- Affected files:
{affected}

- Affected API routes:
{routes if routes else "None"}

Write a clear risk assessment (3-5 sentences) explaining:
1. What kinds of breakage could occur
2. Which areas of the application are most at risk
3. What the developer should test before merging
"""
    risk_explanation = _gemini(prompt)
    steps.append("🤖 Generated risk assessment with Gemini.")

    return {
        "impact": impact,
        "risk_explanation": risk_explanation,
        "steps": steps,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  5. ONBOARDING — Pipeline (no agent)
# ─────────────────────────────────────────────────────────────────────────────

def generate_onboarding(graph_dict: dict) -> dict:
    """Generate an onboarding learning path from graph data.

    Pipeline:
        identify key nodes → Gemini generates learning path

    Returns:
        {"learning_path": str, "steps": list[str]}
    """
    steps: list[str] = []

    # Step 1: Identify core modules from graph
    nodes = graph_dict.get("nodes", [])
    key_nodes = sorted(
        nodes,
        key=lambda n: len(n.get("api_routes", [])) * 3 + len(n.get("functions", [])),
        reverse=True,
    )[:15]
    steps.append(f"📦 Identified {len(key_nodes)} core modules for onboarding.")

    # Step 2: Generate learning path with Gemini
    modules_desc = "\n".join([
        f"- {n['id']} (language: {n.get('language')}, routes: {len(n.get('api_routes',[]))}, functions: {len(n.get('functions',[]))})"
        for n in key_nodes
    ])

    prompt = f"""You are a senior engineer creating an onboarding guide for a new developer joining the team.

Repository core modules:
{modules_desc}

Create a structured learning path with 4-6 modules. For each module:
- Module name and description
- Key files to read
- Core concepts to understand
- Estimated time (30 mins, 1 hour, etc.)
- Suggested exercises

Format as clean markdown with ## headers for each module."""

    learning_path = _gemini(prompt)
    steps.append("📚 Generated onboarding learning path.")

    return {
        "learning_path": learning_path,
        "steps": steps,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Lazy singleton graph cache
# ─────────────────────────────────────────────────────────────────────────────
_graph_cache: dict = {}


def get_or_build_graph(repo_path: str, pre_scanned=None):
    """Return cached dependency graph, or build it.

    Args:
        repo_path:    Repository identifier — a local path, GitHub URL, or slug.
                      Resolved (and cloned on demand) to a local path, which is
                      then used as the cache key. This lets portable deep-link
                      identifiers (GitHub URLs) work on any backend, not just the
                      machine that originally cloned the repo.
        pre_scanned:  Optional pre-scanned list from the scan router.
                      When provided, avoids a second scan + parse pass.
    """
    from utils.graph_builder import build_dependency_graph, graph_to_dict
    from utils.mcp_layer import resolve_repo

    # pre_scanned already carries resolved local paths; only resolve otherwise.
    resolved = repo_path if pre_scanned else resolve_repo(repo_path)
    if resolved not in _graph_cache:
        G = build_dependency_graph(resolved, pre_scanned=pre_scanned)
        _graph_cache[resolved] = {"G": G, "dict": graph_to_dict(G)}
    return _graph_cache[resolved]


def invalidate_graph(repo_path: str):
    _graph_cache.pop(repo_path, None)
