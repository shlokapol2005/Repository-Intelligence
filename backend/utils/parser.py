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
_TSX_PARSER = None   # .ts files (no JSX)
_TSXX_PARSER = None  # .tsx files (JSX + TS types)

try:
    import tree_sitter_javascript as _tsjs
    from tree_sitter import Language, Parser as _TSParser

    _JS_PARSER = _TSParser(Language(_tsjs.language()))
    _TS_AVAILABLE = True

    # TypeScript grammar is a superset of JS syntax (generics, interfaces,
    # enums, decorators, `import type`, typed params/returns) that the plain
    # JS grammar cannot parse — without it, every typed arrow function and
    # any file using TS-only syntax silently fails to parse correctly.
    import tree_sitter_typescript as _tsts

    _TSX_PARSER = _TSParser(Language(_tsts.language_typescript()))
    _TSXX_PARSER = _TSParser(Language(_tsts.language_tsx()))
except Exception:
    pass  # falls back to regex silently


def _parser_for_ext(ext: str):
    """Pick the tree-sitter grammar matching the file extension."""
    if ext == ".tsx" and _TSXX_PARSER is not None:
        return _TSXX_PARSER
    if ext == ".ts" and _TSX_PARSER is not None:
        return _TSX_PARSER
    return _JS_PARSER


# ─────────────────────────────────────────────
#  Python Parser (uses stdlib ast module)
# ─────────────────────────────────────────────

def _iter_scoped_statements(stmts):
    """
    Yield statements in the given block, descending into control-flow
    wrappers (if/for/while/with/try) so conditionally-defined top-level
    functions/classes are still found — but NOT into function or class
    bodies. Without this boundary, a plain `ast.walk()` treats every
    function nested inside another function (or every method nested inside
    a class) as if it were a second, independent top-level/class-level
    symbol, duplicating it across `functions`/`classes[].methods`.
    """
    for stmt in stmts:
        yield stmt
        if isinstance(stmt, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
            yield from _iter_scoped_statements(stmt.body)
            yield from _iter_scoped_statements(getattr(stmt, "orelse", []) or [])
        elif isinstance(stmt, ast.Try):
            yield from _iter_scoped_statements(stmt.body)
            yield from _iter_scoped_statements(stmt.orelse)
            yield from _iter_scoped_statements(stmt.finalbody)
            for handler in stmt.handlers:
                yield from _iter_scoped_statements(handler.body)


def _py_base_name(node) -> str | None:
    """
    Render a Python base-class expression to a dotted name.
      class Dog(Animal)        -> "Animal"
      class M(db.Model)        -> "db.Model"
      class G(Generic[T])      -> "Generic"   (subscript/generic stripped)
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = []
        cur = node
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
            return ".".join(reversed(parts))
        return node.attr
    if isinstance(node, ast.Subscript):
        return _py_base_name(node.value)
    return None


def _extract_params(node) -> list[str]:
    params = []
    if hasattr(node, "args") and node.args:
        for arg in node.args.args:
            if arg.annotation:
                if isinstance(arg.annotation, ast.Name):
                    params.append(arg.annotation.id)
                elif isinstance(arg.annotation, ast.Constant):
                    params.append(str(arg.annotation.value))
    return params


def _extract_routes_into(node, out_routes: list) -> None:
    """API route decorators (FastAPI / Flask / Django)."""
    for decorator in node.decorator_list:
        route = _extract_route_decorator(decorator)
        if route:
            out_routes.append({
                "method": route["method"],
                "path": route["path"],
                "handler": node.name,
                "line": node.lineno,
            })


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

    # Imports can legitimately appear anywhere (inside functions, try/except
    # ImportError, `if TYPE_CHECKING:` blocks, etc.) — an unrestricted walk
    # is correct here, unlike for classes/functions below.
    for node in ast.walk(tree):
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

    # Classes & top-level functions — scoped so nested closures and class
    # methods aren't duplicated into the flat top-level functions list.
    for stmt in _iter_scoped_statements(tree.body):
        if isinstance(stmt, ast.ClassDef):
            methods = []
            for cstmt in _iter_scoped_statements(stmt.body):
                if isinstance(cstmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(cstmt.name)
                    _extract_routes_into(cstmt, result["api_routes"])
            extends = [b for b in (_py_base_name(base) for base in stmt.bases) if b]
            result["classes"].append({
                "name": stmt.name,
                "line": stmt.lineno,
                "methods": methods,
                "extends": extends,
                "implements": [],  # Python has no `implements`; kept for shape parity with JS/TS
            })

        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result["functions"].append({
                "name": stmt.name,
                "line": stmt.lineno,
                "parameters": _extract_params(stmt),
            })
            _extract_routes_into(stmt, result["api_routes"])

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


_TS_EXTS = {".ts", ".tsx"}


# Node types whose *children* live inside a nested function/method scope.
# Used to stop a free-standing arrow/function assignment nested inside another
# function from being counted as a top-level, file-level function.
_FUNCTION_SCOPE_TYPES = {
    "function_declaration", "function", "arrow_function",
    "method_definition", "generator_function", "generator_function_declaration",
}

# Node types that name a base class / interface in a class_heritage clause.
_HERITAGE_REF_TYPES = {
    "identifier", "type_identifier", "member_expression",
    "nested_type_identifier", "generic_type",
}


def _heritage_ref_name(node, src: bytes) -> str:
    """
    Normalize a base-class reference to a bare name, dropping generic args.
    e.g. `Container<T>` -> `Container`, `React.Component` -> `React.Component`.
    """
    return _node_text(node, src).split("<", 1)[0].strip()


def _extract_class_heritage(class_node, src: bytes) -> tuple[list[str], list[str]]:
    """
    Extract (extends, implements) base names from a class_declaration.

    Two grammar shapes are handled:
      - JS grammar:  class_heritage → `extends` keyword + base node directly
      - TS grammar:  class_heritage → extends_clause / implements_clause
    Only direct references are taken (type_arguments contents are skipped, so
    the `T` in `extends Container<T>` is not mistaken for a base class).
    """
    extends: list[str] = []
    implements: list[str] = []

    heritage = next((c for c in class_node.children if c.type == "class_heritage"), None)
    if not heritage:
        return extends, implements

    for child in heritage.children:
        if child.type == "extends_clause":
            for c in child.children:
                if c.type in _HERITAGE_REF_TYPES:
                    extends.append(_heritage_ref_name(c, src))
        elif child.type == "implements_clause":
            for c in child.children:
                if c.type in _HERITAGE_REF_TYPES:
                    implements.append(_heritage_ref_name(c, src))
        elif child.type in _HERITAGE_REF_TYPES:
            # JS shape: base sits directly under class_heritage
            extends.append(_heritage_ref_name(child, src))

    return extends, implements


def _extract_import_clause(clause, module: str, src: bytes, imports: list) -> None:
    """
    Extract default / named / namespace imports from an import_clause node.

    NOTE: in this tree-sitter-javascript/typescript grammar, `import_clause`,
    `named_imports`, and `namespace_import` are unnamed positional children —
    NOT fields — so `child_by_field_name(...)` always returns None for them.
    We must match on `.type` instead.
    """
    for child in clause.children:
        if child.type == "identifier":
            # default import: import Foo from '...'
            imports.append({"module": module, "name": _node_text(child, src), "kind": "default"})

        elif child.type == "namespace_import":
            # import * as fs from '...'  →  last identifier child is the local name
            ns_name = next((c for c in child.children if c.type == "identifier"), None)
            imports.append({
                "module": module,
                "name": _node_text(ns_name, src) if ns_name else None,
                "kind": "namespace",
            })

        elif child.type == "named_imports":
            # import { a, b as c, type d } from '...'
            for spec in child.children:
                if spec.type != "import_specifier":
                    continue
                idents = [c for c in spec.children if c.type == "identifier"]
                if not idents:
                    continue
                name = _node_text(idents[0], src)
                alias = _node_text(idents[1], src) if len(idents) > 1 else None
                imports.append({"module": module, "name": name, "alias": alias, "kind": "named"})


def _extract_export_clause(clause, src: bytes, exports: list) -> None:
    """
    Extract names from `export { a, b as c };`.
    `export_clause` is likewise an unnamed positional child of export_statement.
    """
    for spec in clause.children:
        if spec.type != "export_specifier":
            continue
        idents = [c for c in spec.children if c.type == "identifier"]
        if not idents:
            continue
        # externally-visible name is the alias if present, else the original name
        exports.append(_node_text(idents[1] if len(idents) > 1 else idents[0], src))


def _extract_declared_names(decl_node, src: bytes) -> list[str]:
    """Names bound by a `const/let/var` declaration (handles multi-declarator lists)."""
    names = []
    for child in decl_node.children:
        if child.type == "variable_declarator":
            name_node = child.child_by_field_name("name")
            if name_node and name_node.type == "identifier":
                names.append(_node_text(name_node, src))
    return names


def parse_js_file_treesitter(file_path: str, content: str) -> dict[str, Any]:
    """Parse JS/TS using tree-sitter for accurate AST extraction."""
    ext = Path(file_path).suffix.lower()
    result: dict[str, Any] = {
        "file": file_path,
        "language": "typescript" if ext in _TS_EXTS else "javascript",
        "imports": [],
        "classes": [],
        "functions": [],
        "api_routes": [],
        "exports": [],
        "parser": "tree-sitter",
    }

    src = content.encode("utf-8")
    parser = _parser_for_ext(ext)
    tree = parser.parse(src)
    root = tree.root_node

    HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "all"}
    # Variable name → module mapping (e.g., const router = express.Router())
    # Used to detect route objects beyond hardcoded 'router'/'app' names.
    route_objects: set[str] = {"router", "app"}

    def walk(node, func_depth=0):
        """DFS that also tracks nesting inside function/method bodies, so
        closures defined inside another function aren't mistaken for
        top-level, file-scope declarations."""
        yield node, func_depth
        child_depth = func_depth + 1 if node.type in _FUNCTION_SCOPE_TYPES else func_depth
        for child in node.children:
            yield from walk(child, child_depth)

    for node, depth in walk(root):
        kind = node.type

        # ── ES6 import statements ──────────────────────────────────────────
        # import express from 'express'
        # import { Router } from 'express'
        # import * as fs from 'fs'
        if kind == "import_statement":
            module_node = node.child_by_field_name("source")
            module = _node_text(module_node, src).strip("'\"") if module_node else ""

            clause = next((c for c in node.children if c.type == "import_clause"), None)
            if clause:
                _extract_import_clause(clause, module, src, result["imports"])
            elif module:
                # bare import: import './styles.css'
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
        elif kind == "function_declaration" and depth == 0:
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
            extends, implements = _extract_class_heritage(node, src)
            result["classes"].append({
                "name": _node_text(name_node, src) if name_node else "anonymous",
                "line": _get_line(node),
                "methods": methods,
                "extends": extends,
                "implements": implements,
            })

        # ── Arrow functions & function expressions assigned to variables ───
        # const foo = () => {}  /  const foo = function() {}
        elif kind == "variable_declarator" and depth == 0:
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
                if decl.type in ("lexical_declaration", "variable_declaration"):
                    # export const/let/var x = ...  (possibly multiple declarators)
                    result["exports"].extend(_extract_declared_names(decl, src))
                else:
                    # export function foo() {} / export class Foo {}
                    name_node = decl.child_by_field_name("name")
                    if name_node:
                        result["exports"].append(_node_text(name_node, src))
            # export { a, b as c }
            clause = next((c for c in node.children if c.type == "export_clause"), None)
            if clause:
                _extract_export_clause(clause, src, result["exports"])

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
                            if prop.type == "shorthand_property_identifier":
                                # {a, b} shorthand — the identifier itself is the name
                                result["exports"].append(_node_text(prop, src))
                            elif prop.type == "pair":
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
        "language": "typescript" if Path(file_path).suffix.lower() in _TS_EXTS else "javascript",
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
