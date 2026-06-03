import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
FIXTURE_PATH = BOT_ROOT / "tests" / "fixtures" / "brief_parsing_golden.jsonl"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_parser  # noqa: E402

# Golden-набор проверяет rule-based baseline (+ enrich), без LLM.
P1_MIN_FIELD_RECALL = 0.97
P1_MIN_CASE_PASS_RATE = 0.95


def _load_cases() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _parse_case(case: Dict[str, Any]) -> Dict[str, Any]:
    text = case["text"]
    rule_based = brief_parser.extract_brief_rule_based(text)
    brief_parser._finalize_brief_from_text(rule_based, text)
    brief_parser.brief_stay_enrich.enrich_stay_from_context(rule_based)
    return rule_based


def _value_equal(expected: Any, actual: Any) -> bool:
    if isinstance(expected, list) and isinstance(actual, list):
        return expected == actual
    if isinstance(expected, dict) and isinstance(actual, dict):
        return expected == actual
    return expected == actual


def _get_nested(data: Dict[str, Any], dotted_key: str) -> Any:
    node: Any = data
    for part in dotted_key.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _check_nested_contains(parsed: Dict[str, Any], nested: Dict[str, Any]) -> List[str]:
    failures: List[str] = []
    for dotted_key, required_fragments in nested.items():
        actual = _get_nested(parsed, dotted_key)
        if actual is None:
            failures.append(dotted_key)
            continue
        if dotted_key == "party_preferences" and isinstance(required_fragments, list):
            keys = list(actual.keys()) if isinstance(actual, dict) else []
            for fragment in required_fragments:
                if not any(fragment in key for key in keys):
                    failures.append(f"{dotted_key}:{fragment}")
            continue
        haystack = actual
        if isinstance(haystack, list):
            joined = " ".join(str(item).lower() for item in haystack)
        else:
            joined = str(haystack).lower()
        for fragment in required_fragments:
            if str(fragment).lower() not in joined:
                failures.append(f"{dotted_key}:{fragment}")
    return failures


def evaluate_parsing_quality() -> Dict[str, Any]:
    cases = _load_cases()
    per_case: List[Dict[str, Any]] = []
    total_expected_fields = 0
    matched_fields = 0
    missing_fields_total = 0
    wrong_fields_total = 0
    must_not_have_violations_total = 0
    nested_failures_total = 0

    for case in cases:
        case_id = case["id"]
        expected = case["expected"]
        must_not_have = case.get("must_not_have", [])
        expected_nested = case.get("expected_nested", {})

        parsed = _parse_case(case)
        case_missing: List[str] = []
        case_wrong: List[str] = []
        case_forbidden: List[str] = []
        case_nested: List[str] = []

        for key, expected_value in expected.items():
            total_expected_fields += 1
            if key not in parsed:
                case_missing.append(key)
                continue
            if _value_equal(expected_value, parsed[key]):
                matched_fields += 1
            else:
                case_wrong.append(key)

        for forbidden_key in must_not_have:
            if forbidden_key in parsed:
                case_forbidden.append(forbidden_key)

        if expected_nested:
            case_nested = _check_nested_contains(parsed, expected_nested)
            nested_failures_total += len(case_nested)

        missing_fields_total += len(case_missing)
        wrong_fields_total += len(case_wrong)
        must_not_have_violations_total += len(case_forbidden)

        per_case.append(
            {
                "id": case_id,
                "tags": case.get("tags", []),
                "missing_fields": case_missing,
                "wrong_fields": case_wrong,
                "must_not_have_violations": case_forbidden,
                "nested_failures": case_nested,
                "passed": (
                    not case_missing
                    and not case_wrong
                    and not case_forbidden
                    and not case_nested
                ),
            }
        )

    field_precision = (
        matched_fields / (matched_fields + wrong_fields_total)
        if (matched_fields + wrong_fields_total) > 0
        else 0.0
    )
    field_recall = matched_fields / total_expected_fields if total_expected_fields > 0 else 0.0
    case_pass_rate = (
        sum(1 for row in per_case if row["passed"]) / len(per_case)
        if per_case
        else 0.0
    )

    return {
        "cases_total": len(per_case),
        "cases_passed": sum(1 for row in per_case if row["passed"]),
        "case_pass_rate": case_pass_rate,
        "expected_fields_total": total_expected_fields,
        "matched_fields": matched_fields,
        "missing_fields_total": missing_fields_total,
        "wrong_fields_total": wrong_fields_total,
        "must_not_have_violations_total": must_not_have_violations_total,
        "nested_failures_total": nested_failures_total,
        "field_precision": field_precision,
        "field_recall": field_recall,
        "cases": per_case,
    }


def test_brief_parsing_golden_set() -> None:
    report = evaluate_parsing_quality()

    assert report["missing_fields_total"] == 0, (
        f"Missing fields detected: {report['missing_fields_total']}. "
        f"Details: {[c for c in report['cases'] if c['missing_fields']]}"
    )
    assert report["wrong_fields_total"] == 0, (
        f"Wrong field values detected: {report['wrong_fields_total']}. "
        f"Details: {[c for c in report['cases'] if c['wrong_fields']]}"
    )
    assert report["must_not_have_violations_total"] == 0, (
        "Forbidden inferred fields detected. "
        f"Details: {[c for c in report['cases'] if c['must_not_have_violations']]}"
    )
    assert report["nested_failures_total"] == 0, (
        f"Nested expectations failed: {report['nested_failures_total']}. "
        f"Details: {[c for c in report['cases'] if c['nested_failures']]}"
    )


def test_p1_quality_thresholds() -> None:
    report = evaluate_parsing_quality()
    assert report["field_recall"] >= P1_MIN_FIELD_RECALL
    assert report["case_pass_rate"] >= P1_MIN_CASE_PASS_RATE


if __name__ == "__main__":
    result = evaluate_parsing_quality()
    print("=== Brief Parsing Quality Report (rules + enrich) ===")
    print(f"Cases: {result['cases_passed']}/{result['cases_total']} passed")
    print(f"Field precision: {result['field_precision']:.3f}")
    print(f"Field recall: {result['field_recall']:.3f}")
    print(f"Missing fields: {result['missing_fields_total']}")
    print(f"Wrong fields: {result['wrong_fields_total']}")
    print(f"Forbidden inferred fields: {result['must_not_have_violations_total']}")
    print(f"Nested failures: {result['nested_failures_total']}")
    for row in result["cases"]:
        if row["passed"]:
            continue
        print(f"- {row['id']}")
        if row["missing_fields"]:
            print(f"  missing: {row['missing_fields']}")
        if row["wrong_fields"]:
            print(f"  wrong: {row['wrong_fields']}")
        if row["must_not_have_violations"]:
            print(f"  forbidden: {row['must_not_have_violations']}")
        if row["nested_failures"]:
            print(f"  nested: {row['nested_failures']}")
