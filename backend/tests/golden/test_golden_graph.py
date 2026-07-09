"""
Graph-level golden test — validates cross-file resolution (import edges,
CSS/asset edges, and class-inheritance edges), not just single-file parsing.
mini_repo/ has a known, hand-verified structure.
"""
from pathlib import Path

from utils.graph_builder import build_dependency_graph, build_inheritance_edges

MINI_REPO = Path(__file__).parent / "mini_repo"

EXPECTED_IMPORT_EDGES = {
    ("backend/main.py", "backend/utils/helper.py"),
    ("backend/user_controller.py", "backend/base_controller.py"),
    ("frontend/src/index.jsx", "frontend/src/Button.jsx"),
    # CSS import resolves to an edge (previously silently dropped)
    ("frontend/src/Button.jsx", "frontend/src/Button.css"),
}

EXPECTED_INHERITANCE = {
    ("UserController", "backend/user_controller.py", "BaseController", "backend/base_controller.py"),
}


def test_mini_repo_resolves_expected_edges():
    G = build_dependency_graph(str(MINI_REPO))
    actual_edges = {(u, v) for u, v in G.edges()}
    missing = EXPECTED_IMPORT_EDGES - actual_edges
    assert not missing, f"Dependency graph failed to resolve expected edges: {missing}"


def test_css_import_not_flagged_dead():
    """A CSS file that is imported must not be reported as dead code."""
    from utils.graph_builder import detect_dead_code
    G = build_dependency_graph(str(MINI_REPO))
    dead = {u["file"] for u in detect_dead_code(G)["unused_files"]}
    assert "frontend/src/Button.css" not in dead


def test_cross_file_inheritance_resolves():
    G = build_dependency_graph(str(MINI_REPO))
    actual = {
        (e["child_class"], e["child_file"], e["parent_class"], e["parent_file"])
        for e in build_inheritance_edges(G)
    }
    missing = EXPECTED_INHERITANCE - actual
    assert not missing, f"Inheritance resolution failed for: {missing}"
