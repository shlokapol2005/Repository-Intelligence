"""
Dependency Graph Builder
Builds a directed file dependency graph using networkx.
Nodes = files, Edges = import relationships.
Also tracks API route → handler → class chains.
"""
import json
from pathlib import Path
from typing import Any

import networkx as nx

from utils.scanner import scan_repository, read_file_content
from utils.parser import parse_file


# Filenames that mark a directory as a Python runtime root
_PYTHON_ROOT_MARKERS = {"main.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py"}


def _detect_python_roots(all_nodes: set[str]) -> list[str]:
    """
    Detect directories that act as Python sys.path roots.
    A directory is a root if it directly contains a well-known entrypoint file.
    Returns a list of directory path prefixes (e.g. ['backend']).
    """
    roots: set[str] = set()
    for node in all_nodes:
        p = Path(node)
        if p.name in _PYTHON_ROOT_MARKERS:
            parent = str(p.parent).replace("\\", "/")
            roots.add(parent)
    return list(roots)


def build_dependency_graph(repo_path: str) -> nx.DiGraph:
    """
    Scan a repository, parse all files, and construct a directed dependency graph.

    Nodes carry attributes:
        - language, classes, functions, api_routes, lines, size_bytes

    Edges carry attributes:
        - import_name (what symbol/module is imported)
        - edge_type: "import" | "route_handler"

    Returns:
        networkx.DiGraph
    """
    files = scan_repository(repo_path)
    root = Path(repo_path).resolve()

    G = nx.DiGraph()

    # ── Pass 1: Add all nodes ──────────────────────────────────────────────
    parsed_data: dict[str, dict] = {}

    for file_meta in files:
        rel = file_meta["relative_path"]
        content = read_file_content(file_meta["path"])
        parsed = parse_file(file_meta["path"], content)

        G.add_node(rel, **{
            "language": parsed.get("language", "unknown"),
            "classes": parsed.get("classes", []),
            "functions": parsed.get("functions", []),
            "api_routes": parsed.get("api_routes", []),
            "lines": file_meta["lines"],
            "size_bytes": file_meta["size_bytes"],
            "path": file_meta["path"],
        })

        parsed_data[rel] = parsed

    # ── Pass 2: Resolve imports → edges ───────────────────────────────────
    all_nodes = set(G.nodes())
    python_roots = _detect_python_roots(all_nodes)

    for rel, parsed in parsed_data.items():
        for imp in parsed.get("imports", []):
            module = imp.get("module", "")
            # `name` is the symbol after `from module import <name>`
            # e.g. `from routers import scan`  →  module='routers', name='scan'
            name = imp.get("name", "")
            level = imp.get("level", 0)  # Python relative import level (dots)
            if not module and not name:
                continue

            # Try to resolve the import to an actual file node
            resolved = _resolve_import(
                rel, module, all_nodes, root,
                import_name=name, level=level,
                python_roots=python_roots,
            )
            if resolved and resolved != rel:
                label = f"{module}.{name}" if name else module
                G.add_edge(rel, resolved, import_name=label, edge_type="import")

    return G


def _resolve_import(
    current_file: str,
    module: str,
    all_nodes: set[str],
    root: Path,
    import_name: str = "",
    level: int = 0,
    python_roots: list[str] | None = None,
) -> str | None:
    """
    Attempt to resolve a module import string to a node name in the graph.

    Handles:
    - JS relative imports:        './auth', '../lib/utils'
    - Python relative imports:    `from . import foo`, `from ..utils import bar`
    - Package-style imports:      `from utils.scanner import ...`
    - Subpackage member imports:  `from routers import scan`  →  routers/scan.py
    - Python root-relative:       `utils.scanner` resolved from backend/ root
    """
    current_dir = Path(current_file).parent
    py_exts = [".py"]
    js_exts = [".js", ".jsx", ".ts", ".tsx", "/index.js", "/index.jsx", "/index.ts", "/index.tsx"]
    all_exts = py_exts + js_exts

    candidates: list[str] = []

    # ── 1. JS/CSS relative imports (start with . or ..)
    if module.startswith("."):
        base = module.lstrip("./").replace(".", "/")
        candidates += [str(current_dir / base) + ext for ext in all_exts]

    # ── 2. Python explicit relative imports (level > 0 means dots before module)
    elif level and level > 0:
        # Walk up `level` directories from current file's directory
        rel_root = current_dir
        for _ in range(level - 1):
            rel_root = rel_root.parent
        slug = module.replace(".", "/") if module else ""
        base_dir = str(rel_root / slug) if slug else str(rel_root)
        candidates += [base_dir + ext for ext in py_exts]
        if import_name:
            candidates += [str(Path(base_dir) / import_name) + ext for ext in py_exts]
            # package/__init__.py style
            candidates += [str(Path(base_dir) / import_name / "__init__") + ext for ext in py_exts]

    else:
        # ── 3. Package-style absolute import (dots = directory separators)
        slug = module.replace(".", "/")

        # 3a. Resolve from repo root
        candidates += [slug + ext for ext in all_exts]

        # 3b. If there's an import_name, try module/name  (fixes `from routers import scan`)
        if import_name:
            candidates += [f"{slug}/{import_name}" + ext for ext in all_exts]
            # Also module/name/__init__.py
            candidates += [f"{slug}/{import_name}/__init__" + ext for ext in py_exts]

        # 3c. Resolve from each detected Python runtime root  (fixes `utils.scanner` → backend/utils/scanner.py)
        for py_root in (python_roots or []):
            root_slug = f"{py_root}/{slug}" if py_root and py_root != "." else slug
            candidates += [root_slug + ext for ext in py_exts]
            if import_name:
                candidates += [f"{root_slug}/{import_name}" + ext for ext in py_exts]

        # 3d. Relative to current file's directory (local sibling modules)
        candidates += [str(current_dir / slug) + ext for ext in all_exts]
        if import_name:
            candidates += [str(current_dir / slug / import_name) + ext for ext in py_exts]

    for c in candidates:
        normalized = c.replace("\\", "/").lstrip("/")
        if normalized in all_nodes:
            return normalized

    return None


def graph_to_dict(G: nx.DiGraph) -> dict[str, Any]:
    """
    Serialize the dependency graph to a JSON-friendly dict.
    """
    return {
        "nodes": [
            {
                "id": n,
                "language": data.get("language"),
                "classes": [c["name"] if isinstance(c, dict) else c for c in data.get("classes", [])],
                "functions": [f["name"] if isinstance(f, dict) else f for f in data.get("functions", [])],
                "api_routes": data.get("api_routes", []),
                "lines": data.get("lines"),
                "size_bytes": data.get("size_bytes"),
            }
            for n, data in G.nodes(data=True)
        ],
        "edges": [
            {
                "source": u,
                "target": v,
                "import_name": data.get("import_name"),
                "edge_type": data.get("edge_type", "import"),
            }
            for u, v, data in G.edges(data=True)
        ],
        "stats": {
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
        }
    }


def get_impact(G: nx.DiGraph, file_rel_path: str) -> dict[str, Any]:
    """
    For a given file, find all files that transitively depend on it.
    Used for impact analysis.

    Returns:
        {
            "target": file,
            "affected_files": [...],
            "affected_count": N,
            "affected_routes": [...],
            "risk": "Low" | "Medium" | "High" | "Critical"
        }
    """
    if file_rel_path not in G:
        return {"error": f"File '{file_rel_path}' not found in graph."}

    # Reverse the graph to find what depends ON our target
    RG = G.reverse(copy=True)
    affected = set(nx.descendants(RG, file_rel_path))
    affected_files = sorted(affected)

    # Collect all API routes from affected nodes
    affected_routes = []
    for f in affected_files:
        routes = G.nodes[f].get("api_routes", [])
        for r in routes:
            affected_routes.append({
                "file": f,
                "method": r.get("method"),
                "path": r.get("path"),
            })

    count = len(affected_files)
    if count == 0:
        risk = "Low"
    elif count <= 3:
        risk = "Medium"
    elif count <= 10:
        risk = "High"
    else:
        risk = "Critical"

    return {
        "target": file_rel_path,
        "affected_files": affected_files,
        "affected_count": count,
        "affected_routes": affected_routes,
        "risk": risk,
    }


def detect_dead_code(G: nx.DiGraph) -> dict[str, Any]:
    """
    Detect potentially unused files (nodes with zero in-degree, i.e. nothing imports them).
    Excludes entrypoints by naming convention (main.py, index.js, app.py, etc.).

    Returns:
        {"unused_files": [...], "count": N}
    """
    ENTRYPOINTS = {
        "main.py", "app.py", "server.py", "manage.py",
        "index.js", "index.ts", "index.jsx", "index.tsx",
        "app.js", "app.ts",
    }

    unused = []
    for node, in_deg in G.in_degree():
        filename = Path(node).name
        if in_deg == 0 and filename not in ENTRYPOINTS:
            data = G.nodes[node]
            unused.append({
                "file": node,
                "language": data.get("language"),
                "functions": [f["name"] if isinstance(f, dict) else f for f in data.get("functions", [])],
                "classes": [c["name"] if isinstance(c, dict) else c for c in data.get("classes", [])],
            })

    return {"unused_files": unused, "count": len(unused)}


def generate_mermaid(G: nx.DiGraph, max_nodes: int = 40) -> str:
    """
    Convert the dependency graph into a Mermaid.js flowchart string.
    Limits output to the most connected nodes to keep diagrams readable.
    """
    # Pick top nodes by degree
    top_nodes = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:max_nodes]
    subgraph = G.subgraph(top_nodes)

    lines = ["flowchart TD"]
    safe_id: dict[str, str] = {}

    def node_id(n: str) -> str:
        if n not in safe_id:
            safe_id[n] = f"N{len(safe_id)}"
        return safe_id[n]

    for node in subgraph.nodes():
        label = Path(node).name
        nid = node_id(node)
        data = G.nodes[node]
        if data.get("api_routes"):
            lines.append(f'    {nid}["{label} 🌐"]')
        elif data.get("language") == "python":
            lines.append(f'    {nid}["{label}"]')
        else:
            lines.append(f'    {nid}(["{label}"])')

    for u, v in subgraph.edges():
        lines.append(f"    {node_id(u)} --> {node_id(v)}")

    return "\n".join(lines)
