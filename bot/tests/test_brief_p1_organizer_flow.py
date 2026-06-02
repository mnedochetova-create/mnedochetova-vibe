"""P1: сценарии организатора (multi-step) и missing после enrich."""

import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_parser  # noqa: E402


def _merge_organizer_step(base: dict, text: str) -> dict:
    incoming, _ = brief_parser.parse_message_to_brief(text, role="organizer")
    if brief_parser.brief_completeness_score(base) >= 4:
        return brief_parser.merge_brief_clarify(base, incoming)
    return brief_parser.merge_brief(base, incoming)


def test_organizer_three_step_turkey_flow_missing_empty() -> None:
    brief: dict = {}
    steps = [
        "семейная поездка в Турцию, Бодрум, 3 взрослых и 1 ребенок 8 лет, "
        "неделя с мамой и племянником, 3-4 дня с мужем в другом отеле, загранпаспорта ок",
        "13-23 июня, бюджет гибкий, прямой перелет эконом",
        "бюджет до 400-600к",
    ]
    for text in steps:
        brief = _merge_organizer_step(brief, text)

    missing = brief_parser.missing_brief_fields(brief)
    assert missing == []
    assert brief.get("budget_rub_min") == 400_000
    assert brief.get("budget_rub_max") == 600_000
    assert brief.get("budget_flexible") is True
    se = brief.get("stay_experience") or {}
    setting = " ".join(se.get("setting") or [])
    assert "Бодрум" in setting
    assert brief.get("party_preferences")


def test_organizer_dump_missing_count_at_most_three() -> None:
    text = (
        "семейная поездка в Турцию, Бодрум, 3 взрослых и 1 ребенок, "
        "неделя с мамой, загранпаспорта ок"
    )
    brief, _ = brief_parser.parse_message_to_brief(text, role="organizer")
    missing = brief_parser.missing_brief_fields(brief)
    assert len(missing) <= 3
    assert not any("Сценарий отдыха" in item for item in missing)
