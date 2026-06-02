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


def test_restore_brief_from_organizer_dump() -> None:
    dump = "7 взрослых 1 ребенок конец августа бюджет до 1 млн греция море виза нужна"
    event = {"brief": {}, "organizer_dump": dump}
    restored = brief_parser.restore_organizer_brief_from_event(event)
    assert restored.get("adults") == 7
    assert restored.get("budget_rub_max") == 1_000_000


def test_merge_brief_clarify_keeps_base() -> None:
    base = {
        "adults": 7,
        "kids_count": 1,
        "months": ["август"],
        "budget_rub_max": 1_000_000,
        "climate": "море/пляж",
        "visa_required": True,
    }
    incoming = brief_parser.extract_brief_rule_based(
        "хочу горы и пляж, виноградники"
    )
    merged = brief_parser.merge_brief_clarify(base, incoming)
    assert merged.get("adults") == 7
    assert merged.get("budget_rub_max") == 1_000_000
    assert "гор" in str(merged.get("climate", "")).lower()


def test_merge_brief_ignores_llm_zero_placeholders() -> None:
    base = {
        "adults": 2,
        "kids_count": 1,
        "months": ["июл"],
        "budget_rub_max": 300_000,
    }
    incoming = {
        "transfers_allowed": True,
        "flight_preferences": ["эконом"],
        "adults": 0,
        "budget_rub_max": 0,
        "months": [],
    }
    merged = brief_parser.merge_brief(base, incoming)
    assert merged.get("adults") == 2
    assert merged.get("budget_rub_max") == 300_000
    assert merged.get("months") == ["июл"]
    assert merged.get("transfers_allowed") is True


def test_merge_organizer_incoming_clarify_preserves_base() -> None:
    base = {
        "adults": 2,
        "months": ["июл"],
        "budget_rub_max": 300_000,
    }
    incoming = {
        "transfers_allowed": True,
        "flight_preferences": ["эконом"],
        "adults": 0,
        "budget_rub_max": 0,
    }
    merged = brief_parser.merge_organizer_incoming(
        base,
        incoming,
        flow_step="organizer_clarify",
    )
    assert merged.get("adults") == 2
    assert merged.get("budget_rub_max") == 300_000
    assert merged.get("transfers_allowed") is True


def test_combined_sea_and_mountains_climate() -> None:
    parsed = brief_parser.extract_brief_rule_based(
        "часть времени на виноградниках в горах, часть на пляже"
    )
    assert "море" in str(parsed.get("climate", "")).lower()
    assert "гор" in str(parsed.get("climate", "")).lower()
