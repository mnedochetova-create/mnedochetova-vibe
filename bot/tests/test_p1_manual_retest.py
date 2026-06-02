"""
Автоматический ретест P1 (фаза A) — зеркало docs/Family travel bot/P1_MANUAL_RETEST.md.

Запуск: pytest bot/tests/test_p1_manual_retest.py -v
В CI: вместе с bot/tests/ (см. .github/workflows/bot-tests.yml).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
TESTS_DIR = BOT_ROOT / "tests"
for path in (SRC_DIR, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import brief_display  # noqa: E402
import brief_parser  # noqa: E402
import brief_stay_enrich  # noqa: E402
import main  # noqa: E402

from test_brief_france_family import FRANCE_FAMILY_TEXT  # noqa: E402

pytestmark = pytest.mark.p1_retest


def _merge_organizer_step(base: dict, text: str) -> dict:
    incoming, _ = brief_parser.parse_message_to_brief(text, role="organizer")
    if brief_parser.brief_completeness_score(base) >= 4:
        return brief_parser.merge_brief_clarify(base, incoming)
    return brief_parser.merge_brief(base, incoming)


class TestP1RetestCase1FranceFamily:
    """Кейс 1 — Франция, большая семья (одно сообщение)."""

    @pytest.fixture
    def brief(self) -> dict:
        return brief_parser.extract_brief_from_text(FRANCE_FAMILY_TEXT)

    def test_p1_fields_and_missing(self, brief: dict) -> None:
        missing = brief_parser.missing_brief_fields(brief)
        assert brief.get("budget_eur_max") == 15_000
        assert brief.get("adults") == 6
        assert brief.get("kids_count") == 1
        assert brief.get("trip_title") == "Во Францию с семьёй"
        assert len(missing) == 1
        assert missing[0].startswith("Перелёт")
        assert not any("Визы" in m for m in missing)
        assert not any("разные мнения" in n for n in (brief.get("constraints_notes") or []))

    def test_card_no_insight_visa_or_duplicate_extras(self, brief: dict) -> None:
        brief_stay_enrich.enrich_stay_from_context(brief)
        missing = brief_parser.missing_brief_fields(brief)
        card = main.format_brief_update_message(brief, event_number=1, missing=missing)
        assert "💡" not in card
        assert "Визы" not in card
        assert " · " not in (brief_stay_enrich.format_stay_experience_display(brief) or "")
        extras = brief_display.filter_extra_activity_preferences(
            brief, brief.get("activity_preferences") or []
        )
        assert not any("ресторан" in x.lower() for x in extras)
        if "Дополнительные пожелания" in card:
            assert "ресторан" not in card.lower().split("дополнительные пожелания")[-1][:80]


class TestP1RetestCase2TurkeyThreeSteps:
    """Кейс 2 — Турция Бодрум, 3 шага (из P1_MANUAL_RETEST)."""

    def test_missing_empty_after_step_three(self) -> None:
        brief: dict = {}
        steps = [
            "Турция бодрум, 2 взрослых, июнь, бюджет до 300к, море",
            "перелёт прямой, эконом, до 5 часов",
            "без визы, загран есть",
        ]
        for text in steps:
            brief = _merge_organizer_step(brief, text)
        missing = brief_parser.missing_brief_fields(brief)
        assert missing == []
        se = brief.get("stay_experience") or {}
        setting = " ".join(se.get("setting") or [])
        assert "Бодрум" in setting or "Турция" in setting
        assert brief.get("budget_rub_max") == 300_000
        assert brief.get("flight_hours_max") == 5
        assert brief.get("flight_preferences")


class TestP1RetestCase3UsdBudget:
    """Кейс 3 — бюджет в USD."""

    TEXT = "2 взрослых, июль, Турция, бюджет до 5000 долларов, море и отель"

    def test_budget_not_in_missing_and_card(self) -> None:
        brief = brief_parser.extract_brief_from_text(self.TEXT)
        missing = brief_parser.missing_brief_fields(brief)
        assert brief_parser.budget_is_set(brief)
        assert not any(m.startswith("Бюджет") for m in missing)
        card = main.format_brief_update_message(brief, event_number=2, missing=missing)
        assert "5 000" in card or "5000" in card
        assert "$" in card or "USD" in card.upper()


class TestP1RetestCase4ParticipantContribution:
    """Кейс 4 — участник: пляж + рестораны."""

    PARTICIPANT_TEXT = (
        "хочу песчаный пляж, на машине к достопримечательностям и хорошие рестораны"
    )

    def test_participant_does_not_overwrite_organizer_budget(self) -> None:
        base = {
            "adults": 2,
            "budget_rub_max": 300_000,
            "months": ["июнь"],
            "stay_experience": {"setting": ["Турция", "Бодрум"]},
        }
        incoming = brief_parser.extract_brief_from_text(
            self.PARTICIPANT_TEXT, role="participant"
        )
        merged = brief_parser.merge_participant_into_brief(
            base, incoming, "Участник Тест"
        )
        assert merged.get("budget_rub_max") == 300_000
        assert "Участник Тест" in (merged.get("participant_preferences") or {})
        prefs = merged["participant_preferences"]["Участник Тест"]
        assert prefs.get("activity_preferences")
        assert not prefs.get("budget_rub_max")


class TestP1RetestCase5NewTripVsOldBrief:
    """Кейс 5 — новая поездка не перезаписывает старый полный бриф."""

    def test_resolve_and_merge_target_new_event(self) -> None:
        chat_id = 700001
        main.EVENTS.clear()
        main.EVENTS["trip_old"] = {
            "code": "trip_old",
            "organizer_chat_id": chat_id,
            "updated_at": 100,
            "brief": {
                "adults": 3,
                "months": ["июль"],
                "budget_rub_max": 500_000,
                "flight_hours_max": 5,
                "stay_experience": {"setting": ["Турция", "Бодрум"]},
                "trip_title": "В Турцию с компанией",
            },
        }
        main.EVENTS["trip_new"] = {
            "code": "trip_new",
            "organizer_chat_id": chat_id,
            "updated_at": 200,
            "brief": {},
        }
        code = main.resolve_organizer_event_code(chat_id, "trip_new")
        assert code == "trip_new"

        text = "Греция, август, 2 взрослых, до 200к"
        incoming, _ = brief_parser.parse_message_to_brief(text, role="organizer")
        main.EVENTS[code]["brief"] = brief_parser.merge_brief(
            main.EVENTS[code].get("brief") or {}, incoming
        )
        brief_display.sync_trip_title(main.EVENTS[code]["brief"])

        new_brief = main.EVENTS["trip_new"]["brief"]
        old_brief = main.EVENTS["trip_old"]["brief"]
        assert new_brief.get("budget_rub_max") == 200_000
        assert "Грец" in (new_brief.get("trip_title") or "")
        assert old_brief.get("budget_rub_max") == 500_000
        assert "Бодрум" in " ".join(
            (old_brief.get("stay_experience") or {}).get("setting") or []
        )
