"""
AST Parser
Parses Python and JavaScript/TypeScript files to extract:
- Imports / dependencies
- Classes and methods
- Functions
- API route definitions
- Exports
"""
import ast
import re
from pathlib import Path
from typing import Any


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
    """Extract HTTP method and path from route decorators."""
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
                return {"method": method, "path": first_arg.value}

    return None


# ─────────────────────────────────────────────
#  JavaScript / TypeScript Parser (Regex-based)
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


def parse_js_file(file_path: str, content: str) -> dict[str, Any]:
    """Parse a JavaScript/TypeScript file and extract structural metadata."""
    result = {
        "file": file_path,
        "language": "javascript",
        "imports": [],
        "classes": [],
        "functions": [],
        "api_routes": [],
        "exports": [],
    }

    # Imports
    for m in _JS_IMPORT_RE.finditer(content):
        module = m.group(1) or m.group(2)
        if module:
            result["imports"].append({"module": module})

    # Functions
    for m in _JS_FUNCTION_RE.finditer(content):
        result["functions"].append({"name": m.group(1), "line": content[:m.start()].count("\n") + 1})
    for m in _JS_ARROW_RE.finditer(content):
        result["functions"].append({"name": m.group(1), "line": content[:m.start()].count("\n") + 1})

    # Classes
    for m in _JS_CLASS_RE.finditer(content):
        result["classes"].append({"name": m.group(1), "line": content[:m.start()].count("\n") + 1})

    # Exports
    for m in _JS_EXPORT_RE.finditer(content):
        name = m.group(1)
        if name and name not in ("default", "from"):
            result["exports"].append(name)

    # Express/Next.js API routes
    for m in _EXPRESS_ROUTE_RE.finditer(content):
        result["api_routes"].append({
            "method": m.group(1).upper(),
            "path": m.group(2),
            "line": content[:m.start()].count("\n") + 1,
        })

    return result


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
