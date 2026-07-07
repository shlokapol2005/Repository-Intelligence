"""
Dependency Graph Builder
Builds a directed file dependency graph using networkx.
Nodes = files, Edges = import relationships.
Also tracks API route → handler → class chains.
Supports:
  - JS/TS path alias resolution from tsconfig.json / jsconfig.json
  - Pre-scanned file data to avoid redundant I/O
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


def _load_path_aliases(root: Path) -> dict[str, str]:
    """
    Load JS/TS path aliases from tsconfig.json or jsconfig.json.
    Searches the repo root and one level of subdirectories.

    Returns a dict mapping alias prefix → resolved absolute path prefix.
    Example: {"@": "/abs/path/to/src", "~": "/abs/path/to/src"}
    """
    aliases: dict[str, str] = {}
    config_files = ["tsconfig.json", "jsconfig.json"]

    candidates: list[Path] = []
    for name in config_files:
        candidates.append(root / name)
        for sub in root.iterdir():
            if sub.is_dir() and not sub.name.startswith(".") and sub.name not in (
                "node_modules", ".venv", "venv", "dist", "build", ".next"
            ):
                candidates.append(sub / name)

    for config_path in candidates:
        if not config_path.exists():
            continue
        try:
            with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
                config = json.load(f)
            opts = config.get("compilerOptions", {})
            paths = opts.get("paths", {})
            base_url = opts.get("baseUrl", ".")
            base = (config_path.parent / base_url).resolve()

            for alias_pattern, targets in paths.items():
                if not targets:
                    continue
                # Strip trailing /* to get prefix
                alias_key = alias_pattern.rstrip("/*")
                target_dir = targets[0].rstrip("/*")
                resolved = (base / target_dir).resolve()
                aliases[alias_key] = str(resolved).replace("\\", "/")
        except Exception:
            continue

    return aliases


def build_dependency_graph(
    repo_path: str,
    pre_scanned: list[tuple[dict, str, dict]] | None = None,
) -> nx.DiGraph:
    """
    Scan a repository, parse all files, and construct a directed dependency graph.

    Args:
        repo_path:    Absolute path to the repository root.
        pre_scanned:  Optional list of (file_meta, content, parsed) tuples.
                      When provided, skips the scan + parse phase entirely,
                      reusing already-computed data from the scan router.

    Nodes carry attributes:
        - language, classes, functions, api_routes, lines, size_bytes

    Edges carry attributes:
        - import_name (what symbol/module is imported)
        - edge_type: "import" | "route_handler"

    Returns:
        networkx.DiGraph
    """
    root = Path(repo_path).resolve()

    # Load JS/TS path aliases from tsconfig/jsconfig
    path_aliases = _load_path_aliases(root)

    G = nx.DiGraph()

    # ── Pass 1: Add all nodes ──────────────────────────────────────────────
    parsed_data: dict[str, dict] = {}

    if pre_scanned:
        # Reuse already-computed scan + parse data
        for file_meta, content, parsed in pre_scanned:
            rel = file_meta["relative_path"]
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
    else:
        # Full scan + parse from scratch
        files = scan_repository(repo_path)
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
            name   = imp.get("name", "") or imp.get("alias", "") or ""
            level  = imp.get("level", 0)
            if not module and not name:
                continue

            resolved = _resolve_import(
                rel, module, all_nodes, root,
                import_name=name, level=level,
                python_roots=python_roots,
                path_aliases=path_aliases,
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
    path_aliases: dict[str, str] | None = None,
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

    # ── 0. JS/TS path aliases (@/..., ~/, etc.) ───────────────────────────
    if path_aliases and not module.startswith(".") and level == 0:
        for alias_prefix, alias_target in (path_aliases or {}).items():
            if module == alias_prefix or module.startswith(alias_prefix + "/"):
                suffix = module[len(alias_prefix):].lstrip("/")
                # alias_target is an absolute path string
                alias_resolved = (Path(alias_target) / suffix).as_posix()
                # Try to make it relative to repo root for node lookup
                try:
                    rel_alias = Path(alias_resolved).relative_to(root).as_posix()
                    candidates += [rel_alias + ext for ext in all_exts]
                    if import_name:
                        candidates += [(rel_alias + "/" + import_name + ext) for ext in py_exts]
                except ValueError:
                    pass
                break

    # ── 1. JS/CSS relative imports (start with . or ..)
    if module.startswith("."):
        # Use os.path.normpath to correctly handle ../  paths.
        # The old lstrip("./") was wrong — it stripped individual chars,
        # so "../models/User" → "models/User" instead of the parent directory.
        import os
        base = os.path.normpath(
            os.path.join(str(current_dir), module)
        ).replace("\\", "/")
        candidates += [base + ext for ext in all_exts]

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

    # Create a lowercase mapping of all nodes for case-insensitive lookup (common on Windows/macOS)
    all_nodes_lower = {n.lower(): n for n in all_nodes}

    for c in candidates:
        normalized = c.replace("\\", "/").lstrip("/")
        # Try case-sensitive match first
        if normalized in all_nodes:
            return normalized
        # Fall back to case-insensitive match
        if normalized.lower() in all_nodes_lower:
            return all_nodes_lower[normalized.lower()]

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

    # Collect all API routes from affected nodes AND the target file itself
    affected_routes = []
    for f in affected_files + [file_rel_path]:
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

    A file is considered an entrypoint / standalone (not dead) if:
      - Its name matches known entrypoint conventions (main.py, server.js, index.ts, ...)
      - Its name matches standalone-script patterns (train_*.py, run_*.py, migrate_*.py, seed_*.py)
      - It declares API routes (it's a mounted router — imported indirectly at runtime)
      - It only has a CommonJS "default" export (Mongoose models: module.exports = model(...))

    Returns:
        {"unused_files": [...], "count": N}
    """
    # Known entrypoints — both Python and JS/TS server files
    ENTRYPOINTS = {
        # Python
        "main.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py",
        "conftest.py", "setup.py", "setup.cfg",
        # JavaScript / TypeScript
        "server.js", "server.ts", "server.mjs",
        "index.js", "index.ts", "index.jsx", "index.tsx", "index.mjs",
        "app.js", "app.ts", "app.jsx", "app.tsx",
        "vite.config.js", "vite.config.ts",
        "next.config.js", "next.config.ts",
        "eslint.config.js", "webpack.config.js",
    }

    # Standalone-script name prefixes — these are run directly, not imported
    STANDALONE_PREFIXES = (
        "train_", "run_", "migrate_", "seed_", "generate_", "script_", "cli_",
    )

    unused = []
    for node, in_deg in G.in_degree():
        if in_deg > 0:
            continue  # something imports it — definitely not dead

        filename = Path(node).name
        data = G.nodes[node]

        # Skip known entrypoints
        if filename in ENTRYPOINTS:
            continue

        # Skip standalone scripts by naming convention
        if any(filename.startswith(pfx) for pfx in STANDALONE_PREFIXES):
            continue

        # Skip files that declare API routes — they're mounted at runtime
        if data.get("api_routes"):
            continue

        # Skip Mongoose/ORM models: zero in-degree but exported as "default"
        # These are required() dynamically and the graph can't trace runtime requires.
        exports = data.get("exports", [])
        if "default" in exports and data.get("language") == "javascript":
            continue

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
