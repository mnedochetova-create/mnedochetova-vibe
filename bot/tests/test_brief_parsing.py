import json
import sys
from pathlib import Path
from typing import Any, Dict, List


BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
FIXTURE_PATH = BOT_ROOT / "tests" / "fixtures" / "brief_parsing_golden.jsonl"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import main  # noqa: E402


def _load_cases() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for raw in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _value_equal(expected: Any, actual: Any) -> bool:
    if isinstance(expected, list) and isinstance(actual, list):
        return expected == actual
    if isinstance(expected, dict) and isinstance(actual, dict):
        return expected == actual
    return expected == actual


def evaluate_parsing_quality() -> Dict[str, Any]:
    cases = _load_cases()
    per_case: List[Dict[str, Any]] = []
    total_expected_fields = 0
    matched_fields = 0
    missing_fields_total = 0
    wrong_fields_total = 0
    must_not_have_violations_total = 0

    for case in cases:
        case_id = case["id"]
        text = case["text"]
        expected = case["expected"]
        must_not_have = case.get("must_not_have", [])

        parsed = main.extract_brief_from_text(text)
        case_missing: List[str] = []
        case_wrong: List[str] = []
        case_forbidden: List[str] = []

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
                "passed": not case_missing and not case_wrong and not case_forbidden,
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
        "field_precision": field_precision,
        "field_recall": field_recall,
        "cases": per_case,
    }


def test_brief_parsing_golden_set() -> None:
    report = evaluate_parsing_quality()

    # Fail if there are hard correctness issues.
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


if __name__ == "__main__":
    result = evaluate_parsing_quality()
    print("=== Brief Parsing Quality Report ===")
    print(f"Cases: {result['cases_passed']}/{result['cases_total']} passed")
    print(f"Field precision: {result['field_precision']:.3f}")
    print(f"Field recall: {result['field_recall']:.3f}")
    print(f"Missing fields: {result['missing_fields_total']}")
    print(f"Wrong fields: {result['wrong_fields_total']}")
    print(f"Forbidden inferred fields: {result['must_not_have_violations_total']}")
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
