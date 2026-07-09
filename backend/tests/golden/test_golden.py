"""
Golden parser accuracy suite.

Each fixture in fixtures/<name>.<ext> has a hand-verified expected result in
expected/<name>.json (imports/classes/functions/exports/api_routes). We
parse the fixture with the real parser and diff against that expectation
per field, reporting precision/recall rather than a single pass/fail — see
_compare.py for why.

Run:  pytest tests/golden -v
"""
import json
from pathlib import Path

import pytest

from utils.parser import parse_file
from _compare import diff_fields

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXPECTED_DIR = Path(__file__).parent / "expected"

FIXTURE_FILES = sorted(FIXTURES_DIR.iterdir())


@pytest.mark.parametrize("fixture_path", FIXTURE_FILES, ids=lambda p: p.name)
def test_golden_fixture(fixture_path):
    expected = json.loads((EXPECTED_DIR / f"{fixture_path.stem}.json").read_text())
    content = fixture_path.read_text(encoding="utf-8")
    actual = parse_file(str(fixture_path), content)

    report = diff_fields(expected, actual)
    failures = []
    for field, d in report.items():
        if d["missing"]:
            failures.append(f"{field}: MISSED {sorted(d['missing'])} (recall failure)")
        if d["extra"]:
            failures.append(f"{field}: INVENTED {sorted(d['extra'])} (precision failure)")

    assert not failures, f"{fixture_path.name}:\n  " + "\n  ".join(failures)


def test_accuracy_summary():
    """
    Aggregate precision/recall across the whole fixture set into one number
    per field. This doesn't assert anything strict (individual fixture tests
    above already do that) — it just prints a report you can quote directly,
    e.g. to a stakeholder who wants "how accurate is the parser" as a number.
    """
    from _compare import FIELD_COMPARATORS
    totals = {f: {"tp": 0, "missing": 0, "extra": 0} for f in FIELD_COMPARATORS}

    for fixture_path in FIXTURE_FILES:
        expected = json.loads((EXPECTED_DIR / f"{fixture_path.stem}.json").read_text())
        actual = parse_file(str(fixture_path), fixture_path.read_text(encoding="utf-8"))
        report = diff_fields(expected, actual)
        for field, d in report.items():
            source_key, to_set = FIELD_COMPARATORS[field]
            exp_set = to_set(expected.get(source_key, []))
            totals[field]["tp"] += len(exp_set) - len(d["missing"])
            totals[field]["missing"] += len(d["missing"])
            totals[field]["extra"] += len(d["extra"])

    print("\n\n=== Golden Parser Accuracy Summary ===")
    print(f"{'field':<12} {'recall':>8} {'precision':>10}   (tp / missing / extra)")
    for field, t in totals.items():
        tp, missing, extra = t["tp"], t["missing"], t["extra"]
        recall = tp / (tp + missing) if (tp + missing) else 1.0
        precision = tp / (tp + extra) if (tp + extra) else 1.0
        print(f"{field:<12} {recall:>7.1%} {precision:>9.1%}   ({tp} / {missing} / {extra})")
