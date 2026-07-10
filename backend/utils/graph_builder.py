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
import re
from pathlib import Path
from typing import Any

import networkx as nx

from utils.scanner import scan_repository, read_file_content
from utils.parser import parse_file


# Filenames that mark a directory as a Python runtime root
_PYTHON_ROOT_MARKERS = {"main.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py"}

# ── Canonical entrypoint list ────────────────────────────────────────────────
# Files that are legitimately run/loaded at runtime even when nothing *imports*
# them (so they must never be flagged as dead code). This is the single source
# of truth — dead-code detection, the Mermaid diagram, and the /full graph
# endpoint all read from here, so the definition can't drift between them.
#
# NOTE: `main.*` matters specifically for Vite/bundler frontends, where the real
# entry (`main.jsx`) is referenced from index.html via a <script> tag, not a JS
# import — so it has zero in-edges and would otherwise look "dead".
ENTRYPOINT_NAMES = {
    # Python
    "main.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py",
    "conftest.py", "setup.py",
    # JavaScript / TypeScript app entrypoints
    "main.js", "main.jsx", "main.ts", "main.tsx",
    "index.js", "index.jsx", "index.ts", "index.tsx", "index.mjs",
    "app.js", "app.jsx", "app.ts", "app.tsx",
    "server.js", "server.ts", "server.mjs",
    # Tooling/config entrypoints
    "vite.config.js", "vite.config.ts",
    "next.config.js", "next.config.ts",
    "eslint.config.js", "webpack.config.js",
}


def is_entrypoint(node_or_name: str) -> bool:
    """True if a file path/name is a known runtime entrypoint."""
    return Path(node_or_name).name in ENTRYPOINT_NAMES


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
                "exports": parsed.get("exports", []),
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
                "exports": parsed.get("exports", []),
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
        # Imports that already carry an explicit file extension — CSS/SCSS,
        # assets (svg/png), JSON, or a bare `./foo.js` — should resolve to the
        # literal path itself, not have another extension appended. Without
        # this, `import './Button.css'` never links and the CSS file is wrongly
        # reported as dead code even though a component imports it.
        if Path(module).suffix:
            candidates.append(base)

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


def build_inheritance_edges(G: nx.DiGraph) -> list[dict[str, Any]]:
    """
    Resolve class inheritance (`extends` / `implements`) to cross-file edges.

    This is intentionally kept OUT of the DiGraph itself: impact analysis and
    dead-code detection reason over file *import* edges, and mixing inheritance
    in would distort their results. Instead we return a separate, additive list
    that the architecture view can render as "ClassX extends BaseClass".

    Only intra-repo, unambiguous parents are emitted (a base name that maps to
    exactly one defining file, and never a self-loop). External bases like
    `React.Component` or `APIRouter` are omitted here — they remain visible via
    each class object's own `extends`/`implements` fields.

    Returns list of:
        {child_class, child_file, parent_class, parent_file, relation}
    """
    # class name → set of files that define a class with that name
    class_defs: dict[str, set[str]] = {}
    for node, data in G.nodes(data=True):
        for cls in data.get("classes", []):
            if isinstance(cls, dict) and cls.get("name"):
                class_defs.setdefault(cls["name"], set()).add(node)

    edges: list[dict[str, Any]] = []
    for node, data in G.nodes(data=True):
        for cls in data.get("classes", []):
            if not isinstance(cls, dict):
                continue
            child = cls.get("name")
            for relation, key in (("extends", "extends"), ("implements", "implements")):
                for parent in cls.get(key, []) or []:
                    # base may be dotted (e.g. "db.Model") — match on last segment
                    simple = parent.split(".")[-1]
                    defs = class_defs.get(parent) or class_defs.get(simple)
                    if not defs or len(defs) != 1:
                        continue  # external or ambiguous — skip
                    parent_file = next(iter(defs))
                    if parent_file == node:
                        continue  # self / same-file, not a cross-file edge
                    edges.append({
                        "child_class": child,
                        "child_file": node,
                        "parent_class": parent,
                        "parent_file": parent_file,
                        "relation": relation,
                    })
    return edges


def graph_to_dict(G: nx.DiGraph) -> dict[str, Any]:
    """
    Serialize the dependency graph to a JSON-friendly dict.
    """
    return {
        "inheritance": build_inheritance_edges(G),
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


# Only these are considered "code" for dead-code purposes. Docs, config, JSON,
# CSS, lockfiles etc. are never imported by design — flagging them as "dead
# code" is noise that destroys trust in the feature.
_DEAD_CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

# Path segments that mark test / fixture code — these are run by a test runner
# or read by tests, not imported, so zero in-degree is expected, not "dead".
_TEST_DIR_MARKERS = {"tests", "test", "__tests__", "__mocks__", "fixtures", "mock-repo", "e2e"}


def _is_test_file(node: str) -> bool:
    name = Path(node).name
    parts = set(Path(node).parts)
    if parts & _TEST_DIR_MARKERS:
        return True
    if name in ("conftest.py",):
        return True
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    # JS/TS: foo.test.js, foo.spec.ts, etc.
    stem = name.rsplit(".", 1)[0]
    return stem.endswith(".test") or stem.endswith(".spec")


def detect_dead_code(G: nx.DiGraph) -> dict[str, Any]:
    """
    Detect potentially unused *code* files (zero in-degree — nothing imports them).

    To stay trustworthy, this ONLY considers real source files (.py/.js/.ts/...)
    and skips things that are never imported by design:
      - non-code files (docs, config, JSON, CSS, lockfiles)
      - test files & fixtures (run by a test runner / read by tests)
      - package markers (__init__.py)
      - known entrypoints, standalone scripts, API-route files, and default-only
        CommonJS exports (Mongoose-style models)

    Returns:
        {"unused_files": [...], "count": N}
    """
    # Standalone-script name prefixes — these are run directly, not imported
    STANDALONE_PREFIXES = (
        "train_", "run_", "migrate_", "seed_", "generate_", "script_", "cli_",
    )

    unused = []
    for node, in_deg in G.in_degree():
        if in_deg > 0:
            continue  # something imports it — definitely not dead

        filename = Path(node).name

        # Only real code counts — skip docs/config/data/CSS entirely
        if Path(node).suffix.lower() not in _DEAD_CODE_EXTS:
            continue

        # Skip package markers and test/fixture files (not imported by design)
        if filename == "__init__.py" or _is_test_file(node):
            continue

        data = G.nodes[node]

        # Skip known entrypoints (canonical shared list)
        if filename in ENTRYPOINT_NAMES:
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
        if "default" in exports and data.get("language") in ("javascript", "typescript"):
            continue

        unused.append({
            "file": node,
            "language": data.get("language"),
            "functions": [f["name"] if isinstance(f, dict) else f for f in data.get("functions", [])],
            "classes": [c["name"] if isinstance(c, dict) else c for c in data.get("classes", [])],
        })

    return {"unused_files": unused, "count": len(unused)}


def _mermaid_safe_id(text: str) -> str:
    """A mermaid-safe identifier (letters/digits/underscore only)."""
    return re.sub(r"[^0-9a-zA-Z_]", "_", text) or "root"


def _mermaid_label(text: str) -> str:
    """Escape a label so it can't break mermaid `["..."]` syntax."""
    return text.replace('"', "'").replace("[", "(").replace("]", ")").replace("|", "/")


def generate_mermaid(G: nx.DiGraph, max_nodes: int = 40, direction: str = "TD") -> str:
    """
    Render the dependency graph as a detailed, deterministic Mermaid flowchart.

    Design goals (this output is rendered to a PNG for Discord/Slack, so it must
    be reliable and readable):
      - **Clustered** into subgraphs by directory, so related files group
        together and the layout engine (dagre) spaces clusters apart instead of
        producing one tangled hairball.
      - **Colour-coded** by language via classDef, with distinct styling for API
        route files (thick amber border), entrypoints (🚀) and dead files
        (dashed red) — that's the "detail" without cramming text into nodes.
      - **Overlap-resistant** via an init directive that widens node/rank
        spacing, plus a node cap so huge repos degrade to their most-connected
        files rather than an unreadable mess.

    Args:
        G:          dependency graph.
        max_nodes:  cap on rendered nodes (most-connected win); keeps big repos legible.
        direction:  flowchart direction, "TD" (top-down) or "LR" (left-right).
    """
    if G.number_of_nodes() == 0:
        return "flowchart TD\n    empty[\"(no files parsed)\"]"

    # Code files carry the architecture. Non-code files (docs, config, lockfiles)
    # are only interesting when something actually imports them — otherwise they
    # float as disconnected noise. So: keep all code files; keep non-code files
    # only if they participate in an edge (e.g. an imported .css).
    _CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".css", ".scss"}

    def _eligible(n: str) -> bool:
        if Path(n).suffix.lower() in _CODE_EXTS:
            return True
        return G.degree(n) > 0

    candidates = [n for n in G.nodes() if _eligible(n)]
    total = len(candidates)

    # Most-connected nodes first — these carry the architecture's real structure.
    top_nodes = sorted(candidates, key=lambda n: G.degree(n), reverse=True)[:max_nodes]
    sub = G.subgraph(top_nodes)

    safe_id: dict[str, str] = {}

    def node_id(n: str) -> str:
        if n not in safe_id:
            safe_id[n] = f"N{len(safe_id)}"
        return safe_id[n]

    # ── Group nodes by their parent directory (module cluster) ────────────────
    groups: dict[str, list[str]] = {}
    for node in sub.nodes():
        parent = str(Path(node).parent).replace("\\", "/")
        group = "(root)" if parent in (".", "") else parent
        groups.setdefault(group, []).append(node)

    lines: list[str] = [
        # Wider spacing + smooth edges dramatically reduce visual crowding/overlap.
        "%%{init: {'flowchart': {'nodeSpacing': 55, 'rankSpacing': 70, "
        "'curve': 'basis', 'htmlLabels': true}}}%%",
        f"flowchart {direction}",
        "classDef python fill:#e0e7ff,stroke:#6366f1,stroke-width:1px,color:#1e1b4b;",
        "classDef javascript fill:#cffafe,stroke:#0891b2,stroke-width:1px,color:#083344;",
        "classDef typescript fill:#dbeafe,stroke:#2563eb,stroke-width:1px,color:#172554;",
        "classDef other fill:#f1f5f9,stroke:#64748b,stroke-width:1px,color:#0f172a;",
        "classDef api stroke:#f59e0b,stroke-width:3px;",
        "classDef dead stroke:#ef4444,stroke-width:1px,stroke-dasharray:5 3;",
    ]

    node_classes: dict[str, list[str]] = {}

    # ── Emit one subgraph per directory cluster ───────────────────────────────
    for group in sorted(groups):
        members = groups[group]
        # Show only the trailing 2 path segments to keep cluster titles short.
        title = "/".join(group.split("/")[-2:]) if group != "(root)" else "root"
        lines.append(f'  subgraph cluster_{_mermaid_safe_id(group)}["{_mermaid_label(title)}"]')
        for node in members:
            nid = node_id(node)
            data = G.nodes[node]
            lang = data.get("language", "unknown")
            routes = data.get("api_routes", []) or []
            name = Path(node).name
            is_api = bool(routes)
            is_entry = name in ENTRYPOINT_NAMES
            is_dead = (G.in_degree(node) == 0 and not is_entry and not is_api)

            # No emojis — Kroki's mermaid renderer has no emoji font and would
            # draw "tofu" boxes. Role is conveyed by shape + border colour +
            # a route-count subtitle instead.
            label = _mermaid_label(name)
            if is_api:
                label += f"<br/>{len(routes)} route{'s' if len(routes) != 1 else ''}"

            # Shape: entrypoint = hexagon (distinct), python = box,
            # js/ts/other = rounded. Colour (fill) still comes from classDef.
            if is_entry:
                lines.append(f'    {nid}{{{{"{label}"}}}}')
            elif lang == "python":
                lines.append(f'    {nid}["{label}"]')
            else:
                lines.append(f'    {nid}(["{label}"])')

            classes = [lang if lang in ("python", "javascript", "typescript") else "other"]
            if is_api:
                classes.append("api")
            if is_dead:
                classes.append("dead")
            node_classes[nid] = classes
        lines.append("  end")

    # ── Edges (import relationships) ──────────────────────────────────────────
    for u, v in sub.edges():
        lines.append(f"  {node_id(u)} --> {node_id(v)}")

    # ── Class assignments ─────────────────────────────────────────────────────
    for nid, classes in node_classes.items():
        lines.append(f"  class {nid} {','.join(classes)};")

    if total > len(top_nodes):
        lines.append(f'  note["Showing {len(top_nodes)} of {total} files (most connected)"]')
        lines.append("  class note other;")

    return "\n".join(lines)
