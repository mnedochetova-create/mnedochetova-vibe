import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import brief_parser


def test_merge_brief_preserves_existing_when_incoming_sparse() -> None:
    base = {
        "adults": 7,
        "kids_count": 1,
        "months": ["август"],
        "budget_rub_max": 1_000_000,
        "climate": "море/пляж",
        "activity_preferences": ["предпочтение по направлению: Греция"],
        "visa_required": True,
        "passports_status": "есть",
        "flight_hours_unrestricted": True,
    }
    incoming = brief_parser.extract_brief_rule_based(
        "я бы хотела совместить поездку - часть времени на виноградниках в горах а часть на пляже"
    )
    merged = brief_parser.merge_brief(base, incoming)
    assert merged.get("adults") == 7
    assert merged.get("kids_count") == 1
    assert merged.get("budget_rub_max") == 1_000_000
    assert "август" in (merged.get("months") or [])
    assert merged.get("climate")
    assert "гор" in str(merged.get("climate", "")).lower() or "море" in str(merged.get("climate", "")).lower()


def test_combined_sea_and_mountains_climate() -> None:
    parsed = brief_parser.extract_brief_rule_based(
        "часть времени на виноградниках в горах, часть на пляже"
    )
    assert "море" in str(parsed.get("climate", "")).lower()
    assert "гор" in str(parsed.get("climate", "")).lower()
