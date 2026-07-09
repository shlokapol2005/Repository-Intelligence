"""Shared set-based comparison helpers for golden parser tests.

We compare sets rather than exact structures/order/line-numbers, so the
suite scores *accuracy* (precision/recall per field) instead of failing on
harmless reformatting. This is deliberate: exact-dict equality is brittle
and tends to get "fixed" by weakening the assertion rather than the parser.
"""
from __future__ import annotations


def imports_set(imports: list[dict]) -> set[tuple[str, str]]:
    """(module, symbol) pairs — symbol is name, else alias, else ''."""
    out = set()
    for imp in imports or []:
        module = imp.get("module", "")
        symbol = imp.get("name") or imp.get("alias") or ""
        out.add((module, symbol))
    return out


def names_set(items: list) -> set[str]:
    """For classes/functions lists — each item is a dict with a 'name' key."""
    return {i["name"] if isinstance(i, dict) else i for i in (items or [])}


def exports_set(exports: list[str]) -> set[str]:
    return set(exports or [])


def routes_set(routes: list[dict]) -> set[tuple[str, str]]:
    return {(r.get("method", ""), r.get("path", "")) for r in (routes or [])}


def inheritance_set(classes: list[dict]) -> set[tuple[str, str, str]]:
    """
    Flatten class inheritance into (child_class, base_name, relation) triples,
    so `extends`/`implements` accuracy is scored alongside everything else.
    Reads from the `classes` list (inheritance is nested there, not top-level).
    """
    out = set()
    for cls in classes or []:
        if not isinstance(cls, dict):
            continue
        child = cls.get("name", "")
        for base in cls.get("extends", []) or []:
            out.add((child, base, "extends"))
        for base in cls.get("implements", []) or []:
            out.add((child, base, "implements"))
    return out


# field name → (source key in the parsed dict, set-builder)
FIELD_COMPARATORS = {
    "imports": ("imports", imports_set),
    "classes": ("classes", names_set),
    "functions": ("functions", names_set),
    "exports": ("exports", exports_set),
    "api_routes": ("api_routes", routes_set),
    "inheritance": ("classes", inheritance_set),
}


def diff_fields(expected: dict, actual: dict) -> dict[str, dict[str, set]]:
    """
    Returns, per field, {"missing": set, "extra": set} — empty sets mean a
    perfect match for that field. "missing" = recall failures (parser didn't
    find something real). "extra" = precision failures (parser invented
    something that isn't there).
    """
    report = {}
    for field, (source_key, to_set) in FIELD_COMPARATORS.items():
        exp_set = to_set(expected.get(source_key, []))
        act_set = to_set(actual.get(source_key, []))
        report[field] = {
            "missing": exp_set - act_set,
            "extra": act_set - exp_set,
        }
    return report
