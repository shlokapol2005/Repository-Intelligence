"""
LangGraph Agents
Implements multi-step agent workflows for:
  1. Repository Q&A
  2. Architecture Diagram Generation
  3. Feature Flow Tracing
  4. Impact Analysis
  5. Onboarding Guide Generation
"""
import os
from typing import Any, TypedDict, Annotated
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
    steps: Annotated[list[str], operator.add]


def _qa_retrieve(state: QAState) -> QAState:
    """Step 1: Semantic search for relevant code chunks."""
    chunks = semantic_search(state["question"], state["index_name"], top_k=6)
    return {**state, "retrieved_chunks": chunks, "steps": ["🔍 Searched vector index for relevant chunks."]}


def _qa_read_files(state: QAState) -> QAState:
    """Step 2: Read unique files found in retrieved chunks."""
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
                    "content": result["content"][:3000],  # trim for context window
                })
    return {**state, "file_contents": file_contents, "steps": [f"📂 Read {len(file_contents)} relevant files."]}


def _qa_generate(state: QAState) -> QAState:
    """Step 3: Send context + question to Gemini to generate answer."""
    context_parts = []
    for fc in state["file_contents"]:
        context_parts.append(f"### File: {fc['file']}\n```\n{fc['content']}\n```")

    context = "\n\n".join(context_parts)
    prompt = f"""You are a senior software engineer reviewing a codebase.
Answer the following question using ONLY the provided code context.
Be specific — reference file names, function names, and line patterns.
Format your answer with clear sections and code snippets where helpful.

QUESTION: {state['question']}

CODE CONTEXT:
{context}

Answer:"""

    answer = _gemini(prompt)
    return {**state, "answer": answer, "steps": ["🤖 Generated answer using Gemini."]}


def build_qa_agent():
    g = StateGraph(QAState)
    g.add_node("retrieve", _qa_retrieve)
    g.add_node("read_files", _qa_read_files)
    g.add_node("generate", _qa_generate)
    g.set_entry_point("retrieve")
    g.add_edge("retrieve", "read_files")
    g.add_edge("read_files", "generate")
    g.add_edge("generate", END)
    return g.compile()


# ─────────────────────────────────────────────────────────────────────────────
#  2. ARCHITECTURE DIAGRAM AGENT
# ─────────────────────────────────────────────────────────────────────────────

class ArchState(TypedDict):
    repo_path: str
    graph_dict: dict
    mermaid_raw: str
    mermaid_enhanced: str
    summary: str
    steps: Annotated[list[str], operator.add]


def _arch_to_mermaid(state: ArchState) -> ArchState:
    """Step 1: Convert dependency graph to base Mermaid diagram."""
    from utils.graph_builder import build_dependency_graph, generate_mermaid
    G = build_dependency_graph(state["repo_path"])
    mermaid = generate_mermaid(G)
    return {**state, "mermaid_raw": mermaid, "steps": ["📊 Generated dependency graph and base Mermaid diagram."]}


def _arch_enhance(state: ArchState) -> ArchState:
    """Step 2: Ask Gemini to add labels and improve readability."""
    import re
    prompt = f"""You are a software architect. Here is a raw Mermaid.js flowchart of a codebase's file dependencies:

```mermaid
{state['mermaid_raw']}
```

Your task:
1. Return an improved Mermaid flowchart that:
   - Groups related files into subgraphs (Frontend, Backend, Utils, API, etc.)
   - Uses descriptive, human-readable node labels
   - Highlights API route nodes distinctly
2. Also write a short 3-sentence architecture summary below the diagram.

Return ONLY valid Mermaid syntax for the diagram first, then the summary starting with "## Summary".
"""
    response = _gemini(prompt)
    # Split response into diagram + summary
    if "## Summary" in response:
        parts = response.split("## Summary", 1)
        raw_diagram = parts[0].strip()
        summary = parts[1].strip()
    else:
        raw_diagram = response.strip()
        summary = ""

    # Properly strip ```mermaid ... ``` fences (str.strip() removes chars, not substrings)
    mermaid_enhanced = re.sub(r"^```mermaid\s*", "", raw_diagram, flags=re.IGNORECASE)
    mermaid_enhanced = re.sub(r"\s*```$", "", mermaid_enhanced).strip()

    if not mermaid_enhanced:
        mermaid_enhanced = state["mermaid_raw"]

    return {**state, "mermaid_enhanced": mermaid_enhanced, "summary": summary, "steps": ["✨ Enhanced architecture diagram with Gemini."]}



def build_arch_agent():
    g = StateGraph(ArchState)
    g.add_node("to_mermaid", _arch_to_mermaid)
    g.add_node("enhance", _arch_enhance)
    g.set_entry_point("to_mermaid")
    g.add_edge("to_mermaid", "enhance")
    g.add_edge("enhance", END)
    return g.compile()


# ─────────────────────────────────────────────────────────────────────────────
#  3. FEATURE FLOW TRACER AGENT
# ─────────────────────────────────────────────────────────────────────────────

class FlowState(TypedDict):
    feature: str
    repo_path: str
    index_name: str
    search_results: list[dict]
    trace: list[dict]
    explanation: str
    steps: Annotated[list[str], operator.add]


def _flow_search(state: FlowState) -> FlowState:
    """Step 1: Search for feature entry points via Code Search MCP."""
    results = code_search_mcp(
        query=state["feature"],
        repo_root=state["repo_path"],
        extensions=[".py", ".js", ".jsx", ".ts", ".tsx"],
        max_results=20,
    )
    matches = results.get("matches", [])
    return {**state, "search_results": matches, "steps": [f"🔎 Found {len(matches)} code references for '{state['feature']}'"]}


def _flow_trace(state: FlowState) -> FlowState:
    """Step 2: Read matched files and ask Gemini to trace the flow."""
    seen_files = {}
    for match in state["search_results"][:8]:
        fpath = match["file"]
        if fpath not in seen_files:
            result = filesystem_mcp_read(fpath, state["repo_path"])
            if result.get("success"):
                seen_files[fpath] = result["content"][:2500]

    context = "\n\n".join([f"### {f}\n```\n{c}\n```" for f, c in seen_files.items()])
    prompt = f"""You are a software engineer tracing a feature through a codebase.
Feature to trace: "{state['feature']}"

Relevant code files:
{context}

Task: Trace the full flow for this feature from the frontend/entry point to the database/external service.
Format as a numbered step-by-step trace, like:
1. File: Checkout.jsx → User clicks "Pay"
2. File: api/routes.js → POST /payment
3. File: PaymentController.py → calls PaymentService
4. File: PaymentService.py → calls Stripe API
5. External: Stripe API → returns token
6. File: db/models.py → saves transaction

Be specific with file names and function names. End with a brief explanation."""

    explanation = _gemini(prompt)
    return {**state, "explanation": explanation, "steps": ["🔗 Traced feature flow using Gemini."]}


def build_flow_agent():
    g = StateGraph(FlowState)
    g.add_node("search", _flow_search)
    g.add_node("trace", _flow_trace)
    g.set_entry_point("search")
    g.add_edge("search", "trace")
    g.add_edge("trace", END)
    return g.compile()


# ─────────────────────────────────────────────────────────────────────────────
#  4. IMPACT ANALYSIS AGENT
# ─────────────────────────────────────────────────────────────────────────────

class ImpactState(TypedDict):
    target_file: str
    repo_path: str
    graph: Any
    impact_raw: dict
    risk_explanation: str
    steps: Annotated[list[str], operator.add]


def _impact_traverse(state: ImpactState) -> ImpactState:
    """Step 1: Run graph traversal to find affected files."""
    impact = get_impact(state["graph"], state["target_file"])
    return {**state, "impact_raw": impact, "steps": ["📈 Ran graph traversal to find affected files."]}


def _impact_explain(state: ImpactState) -> ImpactState:
    """Step 2: Use Gemini to explain the impact in plain language."""
    impact = state["impact_raw"]
    if "error" in impact:
        return {**state, "risk_explanation": impact["error"], "steps": ["❌ File not found in graph."]}

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
    explanation = _gemini(prompt)
    return {**state, "risk_explanation": explanation, "steps": ["🤖 Generated risk assessment with Gemini."]}


def build_impact_agent():
    g = StateGraph(ImpactState)
    g.add_node("traverse", _impact_traverse)
    g.add_node("explain", _impact_explain)
    g.set_entry_point("traverse")
    g.add_edge("traverse", "explain")
    g.add_edge("explain", END)
    return g.compile()


# ─────────────────────────────────────────────────────────────────────────────
#  5. ONBOARDING AGENT
# ─────────────────────────────────────────────────────────────────────────────

class OnboardState(TypedDict):
    repo_path: str
    graph_dict: dict
    learning_path: str
    steps: Annotated[list[str], operator.add]


def _onboard_analyze(state: OnboardState) -> OnboardState:
    """Step 1: Identify core modules from graph."""
    nodes = state["graph_dict"].get("nodes", [])
    # Sort by number of API routes + functions — likely to be core
    key_nodes = sorted(
        nodes,
        key=lambda n: len(n.get("api_routes", [])) * 3 + len(n.get("functions", [])),
        reverse=True,
    )[:15]
    return {**state, "steps": [f"📦 Identified {len(key_nodes)} core modules for onboarding."], "_key_nodes": key_nodes}


def _onboard_generate(state: OnboardState) -> OnboardState:
    """Step 2: Generate a structured learning path using Gemini."""
    key_nodes = state.get("_key_nodes", [])
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
    return {**state, "learning_path": learning_path, "steps": ["📚 Generated onboarding learning path."]}


def build_onboard_agent():
    g = StateGraph(OnboardState)
    g.add_node("analyze", _onboard_analyze)
    g.add_node("generate", _onboard_generate)
    g.set_entry_point("analyze")
    g.add_edge("analyze", "generate")
    g.add_edge("generate", END)
    return g.compile()


# ─────────────────────────────────────────────────────────────────────────────
#  Lazy singleton graph cache
# ─────────────────────────────────────────────────────────────────────────────
_graph_cache: dict[str, Any] = {}


def get_or_build_graph(repo_path: str):
    from utils.graph_builder import build_dependency_graph, graph_to_dict
    if repo_path not in _graph_cache:
        G = build_dependency_graph(repo_path)
        _graph_cache[repo_path] = {"G": G, "dict": graph_to_dict(G)}
    return _graph_cache[repo_path]


def invalidate_graph(repo_path: str):
    _graph_cache.pop(repo_path, None)
