"""
AST Parser
Parses Python and JavaScript/TypeScript files to extract:
- Imports / dependencies (ES6 + CommonJS require, with aliases)
- Classes and methods (including Mongoose schema patterns)
- Functions (named, arrow, async)
- API route definitions (router.get/post/..., app.use() mounts)
- Exports (ES6 export + module.exports)

JS/TS uses tree-sitter for accurate AST parsing.
Falls back to regex if tree-sitter is not installed.
"""
import ast
import re
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────
#  tree-sitter bootstrap (optional dependency)
# ─────────────────────────────────────────────

_TS_AVAILABLE = False
_JS_PARSER = None
_JS_LANGUAGE = None

try:
    import tree_sitter_javascript as _tsjs
    from tree_sitter import Language, Parser as _TSParser

    _JS_LANGUAGE = Language(_tsjs.language())
    _JS_PARSER = _TSParser(_JS_LANGUAGE)
    _TS_AVAILABLE = True
except Exception:
    pass  # falls back to regex silently


# ─────────────────────────────────────────────
#  Python Parser (uses stdlib ast module)
# ─────────────────────────────────────────────

def parse_python_file(file_path: str, content: str) -> dict[str, Any]:
    """Parse a Python file and extract structural metadata."""
    result = {
        "file": file_path,
        "language": "python",
        "imports": [],
        "classes": [],
        "functions": [],
        "api_routes": [],
        "calls": [],
    }

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return result

    for node in ast.walk(tree):
        # Imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append({"module": alias.name, "alias": alias.asname})

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                result["imports"].append({
                    "module": module,
                    "name": alias.name,
                    "alias": alias.asname,
                    "level": node.level,
                })

        # Classes
        elif isinstance(node, ast.ClassDef):
            methods = [
                n.name for n in ast.walk(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n != node
            ]
            result["classes"].append({
                "name": node.name,
                "line": node.lineno,
                "methods": methods,
            })

        # Top-level functions (both def and async def)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(node.col_offset, int):
            params = []
            if hasattr(node, "args") and node.args:
                for arg in node.args.args:
                    if arg.annotation:
                        if isinstance(arg.annotation, ast.Name):
                            params.append(arg.annotation.id)
                        elif isinstance(arg.annotation, ast.Constant):
                            params.append(str(arg.annotation.value))
            result["functions"].append({
                "name": node.name,
                "line": node.lineno,
                "parameters": params,
            })

        # API route decorators (FastAPI / Flask / Django)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                route = _extract_route_decorator(decorator)
                if route:
                    result["api_routes"].append({
                        "method": route["method"],
                        "path": route["path"],
                        "handler": node.name,
                        "line": node.lineno,
                    })

    return result


def _extract_route_decorator(decorator: ast.expr) -> dict | None:
    """Extract HTTP method and path from route decorators.
    Handles @app.route('/path', methods=['GET', 'POST']) properly.
    """
    HTTP_METHODS = {"get", "post", "put", "patch", "delete", "route", "options"}

    if isinstance(decorator, ast.Call):
        func = decorator.func
        method = None
        if isinstance(func, ast.Attribute) and func.attr.lower() in HTTP_METHODS:
            method = func.attr.upper()
        elif isinstance(func, ast.Name) and func.id.lower() in HTTP_METHODS:
            method = func.id.upper()

        if method and decorator.args:
            first_arg = decorator.args[0]
            if isinstance(first_arg, ast.Constant):
                path = first_arg.value
                # For Flask @app.route(), try to extract the actual methods list
                if method == "ROUTE":
                    actual_method = _extract_flask_methods(decorator.keywords)
                    method = actual_method or "GET"
                return {"method": method, "path": path}

    return None


def _extract_flask_methods(keywords: list) -> str | None:
    """Extract methods from Flask @app.route(methods=['POST']) keyword arg."""
    for kw in keywords:
        if kw.arg == "methods":
            val = kw.value
            if isinstance(val, ast.List) and val.elts:
                first = val.elts[0]
                if isinstance(first, ast.Constant):
                    return str(first.value).upper()
    return None


# ─────────────────────────────────────────────────────────────
#  JavaScript / TypeScript Parser — Tree-sitter (preferred)
# ─────────────────────────────────────────────────────────────

def _node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _get_line(node) -> int:
    return node.start_point[0] + 1  # tree-sitter is 0-indexed


def parse_js_file_treesitter(file_path: str, content: str) -> dict[str, Any]:
    """Parse JS/TS using tree-sitter for accurate AST extraction."""
    result: dict[str, Any] = {
        "file": file_path,
        "language": "javascript",
        "imports": [],
        "classes": [],
        "functions": [],
        "api_routes": [],
        "exports": [],
        "parser": "tree-sitter",
    }

    src = content.encode("utf-8")
    tree = _JS_PARSER.parse(src)
    root = tree.root_node

    HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "all"}
    # Variable name → module mapping (e.g., const router = express.Router())
    # Used to detect route objects beyond hardcoded 'router'/'app' names.
    route_objects: set[str] = {"router", "app"}

    def walk(node):
        yield node
        for child in node.children:
            yield from walk(child)

    for node in walk(root):
        kind = node.type

        # ── ES6 import statements ──────────────────────────────────────────
        # import express from 'express'
        # import { Router } from 'express'
        # import * as fs from 'fs'
        if kind == "import_statement":
            module_node = node.child_by_field_name("source")
            module = _node_text(module_node, src).strip("'\"") if module_node else ""

            # Find the import clause to extract the local name / named imports
            clause = node.child_by_field_name("import_clause")
            if clause:
                # default import: import X from '...'
                default = clause.child_by_field_name("name")
                if default:
                    result["imports"].append({
                        "module": module,
                        "name": _node_text(default, src),
                        "kind": "default",
                    })
                # named: import { a, b } from '...'
                named_clause = clause.child_by_field_name("named_imports")
                if named_clause:
                    for spec in named_clause.children:
                        if spec.type == "import_specifier":
                            nm = spec.child_by_field_name("name")
                            alias = spec.child_by_field_name("alias")
                            if nm:
                                result["imports"].append({
                                    "module": module,
                                    "name": _node_text(nm, src),
                                    "alias": _node_text(alias, src) if alias else None,
                                    "kind": "named",
                                })
                # namespace: import * as X from '...'
                ns = clause.child_by_field_name("namespace_import")
                if ns:
                    result["imports"].append({
                        "module": module,
                        "kind": "namespace",
                    })
            else:
                # bare import: import './styles.css'
                if module:
                    result["imports"].append({"module": module, "kind": "bare"})

        # ── CommonJS require() ─────────────────────────────────────────────
        # const X = require('module')
        # const { a, b } = require('module')
        elif kind in ("lexical_declaration", "variable_declaration"):
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    val_node = child.child_by_field_name("value")
                    if val_node:
                        req_mod = _extract_require(val_node, src)
                        if req_mod:
                            local_name = _node_text(name_node, src) if name_node else None
                            result["imports"].append({
                                "module": req_mod,
                                "alias": local_name,
                                "kind": "require",
                            })
                            # Track known route-like objects
                            # e.g. const authRouter = express.Router()
                            if local_name and "router" in local_name.lower():
                                route_objects.add(local_name)

        # ── Function declarations ──────────────────────────────────────────
        # function foo() {}  /  async function foo() {}
        elif kind == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                result["functions"].append({
                    "name": _node_text(name_node, src),
                    "line": _get_line(node),
                    "kind": "declaration",
                    "async": any(c.type == "async" for c in node.children),
                })

        # ── Class declarations ─────────────────────────────────────────────
        elif kind == "class_declaration":
            name_node = node.child_by_field_name("name")
            body = node.child_by_field_name("body")
            methods = []
            if body:
                for mnode in body.children:
                    if mnode.type == "method_definition":
                        mname = mnode.child_by_field_name("name")
                        if mname:
                            methods.append(_node_text(mname, src))
            result["classes"].append({
                "name": _node_text(name_node, src) if name_node else "anonymous",
                "line": _get_line(node),
                "methods": methods,
            })

        # ── Arrow functions & function expressions assigned to variables ───
        # const foo = () => {}  /  const foo = function() {}
        elif kind == "variable_declarator":
            name_node = node.child_by_field_name("name")
            val_node = node.child_by_field_name("value")
            if name_node and val_node and val_node.type in ("arrow_function", "function"):
                func_name = _node_text(name_node, src)
                # Don't double-count if it was already picked up as a require
                already_import = any(
                    imp.get("alias") == func_name for imp in result["imports"]
                )
                if not already_import:
                    result["functions"].append({
                        "name": func_name,
                        "line": _get_line(node),
                        "kind": "arrow" if val_node.type == "arrow_function" else "expression",
                        "async": any(c.type == "async" for c in val_node.children),
                    })

        # ── Express route calls ────────────────────────────────────────────
        # router.get('/path', handler)
        # app.use('/prefix', routerVar)
        elif kind == "call_expression":
            func = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            if func and func.type == "member_expression":
                obj = func.child_by_field_name("object")
                prop = func.child_by_field_name("property")
                if obj and prop:
                    obj_name = _node_text(obj, src)
                    method_name = _node_text(prop, src).lower()

                    # Route method: router.get/post/put/patch/delete/all
                    if obj_name in route_objects and method_name in HTTP_METHODS:
                        path = _extract_first_string_arg(args, src)
                        if path:
                            result["api_routes"].append({
                                "method": method_name.upper(),
                                "path": path,
                                "line": _get_line(node),
                                "object": obj_name,
                            })

                    # Route mounting: app.use('/prefix', routerVar)
                    elif obj_name in route_objects and method_name == "use":
                        path = _extract_first_string_arg(args, src)
                        if path:
                            result["api_routes"].append({
                                "method": "MOUNT",
                                "path": path,
                                "line": _get_line(node),
                                "object": obj_name,
                            })

        # ── ES6 exports ────────────────────────────────────────────────────
        elif kind in ("export_statement", "export_default_statement"):
            decl = node.child_by_field_name("declaration")
            if decl:
                name_node = decl.child_by_field_name("name")
                if name_node:
                    result["exports"].append(_node_text(name_node, src))
            # export { a, b }
            clause = node.child_by_field_name("export_clause")
            if clause:
                for spec in clause.children:
                    if spec.type == "export_specifier":
                        nm = spec.child_by_field_name("name")
                        if nm:
                            result["exports"].append(_node_text(nm, src))

        # ── CommonJS module.exports ────────────────────────────────────────
        # module.exports = X
        # module.exports = { a, b }
        elif kind == "assignment_expression":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left and _node_text(left, src) in ("module.exports", "exports"):
                if right:
                    rtype = right.type
                    if rtype == "identifier":
                        result["exports"].append(_node_text(right, src))
                    elif rtype == "object":
                        for prop in right.children:
                            if prop.type in ("pair", "shorthand_property_identifier"):
                                key = prop.child_by_field_name("key")
                                if key:
                                    result["exports"].append(_node_text(key, src))
                    else:
                        # e.g. module.exports = function() {} or class
                        name_n = right.child_by_field_name("name")
                        if name_n:
                            result["exports"].append(_node_text(name_n, src))
                        else:
                            result["exports"].append("default")

    return result


def _extract_require(val_node, src: bytes) -> str | None:
    """Extract the module string from a require() call node."""
    if val_node.type == "call_expression":
        func = val_node.child_by_field_name("function")
        args = val_node.child_by_field_name("arguments")
        if func and _node_text(func, src) == "require":
            return _extract_first_string_arg(args, src)
    # Handle dotenv: require('dotenv').config()
    if val_node.type == "member_expression":
        obj = val_node.child_by_field_name("object")
        if obj:
            return _extract_require(obj, src)
    return None


def _extract_first_string_arg(args_node, src: bytes) -> str | None:
    """Get the first string literal argument from an arguments node."""
    if not args_node:
        return None
    for child in args_node.children:
        if child.type == "string":
            return _node_text(child, src).strip("'\"` ")
    return None


# ─────────────────────────────────────────────
#  Regex Fallback (if tree-sitter unavailable)
# ─────────────────────────────────────────────

_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[\w*{},\s]+from\s+)?['"]([^'"]+)['"]"""
    r"""|require\(['"]([^'"]+)['"]\))""",
    re.MULTILINE,
)
_JS_FUNCTION_RE = re.compile(
    r"""(?:export\s+)?(?:async\s+)?function\s+([\w$]+)\s*\(""",
    re.MULTILINE,
)
_JS_ARROW_RE = re.compile(
    r"""(?:export\s+)?(?:const|let|var)\s+([\w$]+)\s*=\s*(?:async\s*)?\(""",
    re.MULTILINE,
)
_JS_CLASS_RE = re.compile(
    r"""(?:export\s+)?class\s+([\w$]+)""",
    re.MULTILINE,
)
_JS_EXPORT_RE = re.compile(
    r"""export\s+(?:default\s+)?(?:const|let|var|function|class)?\s*([\w$]+)""",
    re.MULTILINE,
)
_EXPRESS_ROUTE_RE = re.compile(
    r"""(?:router|app)\.(get|post|put|patch|delete)\s*\(\s*['"`]([^'"`]+)['"`]""",
    re.MULTILINE | re.IGNORECASE,
)


def parse_js_file_regex(file_path: str, content: str) -> dict[str, Any]:
    """Regex-based JS parser (fallback only)."""
    result: dict[str, Any] = {
        "file": file_path,
        "language": "javascript",
        "imports": [],
        "classes": [],
        "functions": [],
        "api_routes": [],
        "exports": [],
        "parser": "regex-fallback",
    }
    for m in _JS_IMPORT_RE.finditer(content):
        module = m.group(1) or m.group(2)
        if module:
            result["imports"].append({"module": module})
    for m in _JS_FUNCTION_RE.finditer(content):
        result["functions"].append({"name": m.group(1), "line": content[:m.start()].count("\n") + 1})
    for m in _JS_ARROW_RE.finditer(content):
        result["functions"].append({"name": m.group(1), "line": content[:m.start()].count("\n") + 1})
    for m in _JS_CLASS_RE.finditer(content):
        result["classes"].append({"name": m.group(1), "line": content[:m.start()].count("\n") + 1})
    for m in _JS_EXPORT_RE.finditer(content):
        name = m.group(1)
        if name and name not in ("default", "from"):
            result["exports"].append(name)
    for m in _EXPRESS_ROUTE_RE.finditer(content):
        result["api_routes"].append({
            "method": m.group(1).upper(),
            "path": m.group(2),
            "line": content[:m.start()].count("\n") + 1,
        })
    return result


def parse_js_file(file_path: str, content: str) -> dict[str, Any]:
    """Dispatch to tree-sitter parser, fall back to regex if unavailable."""
    if _TS_AVAILABLE:
        return parse_js_file_treesitter(file_path, content)
    return parse_js_file_regex(file_path, content)


# ─────────────────────────────────────────────
#  Unified Parser Entry Point
# ─────────────────────────────────────────────

def parse_file(file_path: str, content: str) -> dict[str, Any]:
    """
    Parse any supported file and return structured AST metadata.
    Dispatches to the correct parser based on extension.
    """
    ext = Path(file_path).suffix.lower()
    if ext == ".py":
        return parse_python_file(file_path, content)
    elif ext in {".js", ".jsx", ".ts", ".tsx"}:
        return parse_js_file(file_path, content)
    else:
        return {
            "file": file_path,
            "language": "unknown",
            "imports": [],
            "classes": [],
            "functions": [],
            "api_routes": [],
        }
