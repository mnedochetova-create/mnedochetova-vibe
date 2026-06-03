"""Наземная поездка по России (кейс Olga @olgaroshchina)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import brief_domestic_route
import brief_display
import brief_parser
import brief_stay_enrich
import brief_transport
from brief_display import format_transport_display, transport_field_label

OLGA_FIRST = (
    "2 взрослых, 4 детей, июль, путешествие примерно 2-15 июля, "
    "города центральной России: Ивановская область, Владимирская область, "
    "Нижегородская область. Обязательно к посещению Палех, Гороховец, Дивеево. "
    "Проживание в необычных и уединенных домиках, условия с кухней."
)


def test_olga_first_message_route_and_stay():
    brief = brief_parser.extract_brief_from_text(OLGA_FIRST, role="organizer")
    assert brief.get("adults") == 2
    assert brief.get("kids_count") == 4
    assert brief.get("trip_transport") == brief_transport.TRIP_TRANSPORT_GROUND
    assert "Ивановская область" in (brief.get("regions") or [])
    assert "Палех" in (brief.get("must_visit_places") or [])
    missing = brief_parser.missing_brief_fields(brief)
    assert not any("Перелёт" in m for m in missing)
    assert not any("перелёт" in m.lower() for m in missing)
    assert transport_field_label(brief) == "Передвижение"


def test_olga_display_title_scenario_and_dates():
    brief = brief_parser.finalize_organizer_brief(
        brief_parser.extract_brief_from_text(OLGA_FIRST, role="organizer")
    )
    title = brief_display.derive_trip_title(brief)
    assert "Автопутешествие" in title
    assert "семья 2+4" in title
    assert "Во Иванов" not in title
    assert "примерно" not in brief_domestic_route.format_dates_display(brief).lower()

    scenario = brief_stay_enrich.format_stay_experience_display(brief)
    assert "[" not in scenario
    assert "област" in scenario.lower() or "Иванов" in scenario
    assert "Автопутешествие" in scenario

    acc = brief_domestic_route.format_accommodation_line(brief)
    assert acc
    assert "домик" in acc.lower() or "кухн" in acc.lower() or "уедин" in acc.lower()


def test_olga_stale_brief_without_accommodation_style():
    """Сохранённый бриф без accommodation_style, но с organizer_dump — проживание из текста."""
    polluted = {
        "adults": 2,
        "kids_count": 4,
        "date_range_raw": "примерно 2-15 июля",
        "budget_rub_max": 200_000,
        "trip_title": "Во Ивановская область с семьёй",
        "regions": ["Ивановская область", "Владимирская область", "Нижегородская область"],
        "must_visit_places": ["Палех", "Гороховец", "Дивеево"],
        "trip_transport": "ground",
        "stay_experience": {"setting": ["Москва"], "trip_style": ["экскурсии"]},
        "destination_primary": "Москва",
    }
    restored = brief_parser.restore_organizer_brief_from_event(
        {"brief": polluted, "organizer_dump": OLGA_FIRST}
    )
    assert "Автопутешествие" in restored.get("trip_title", "")
    assert "Москва" not in brief_stay_enrich.format_stay_experience_display(restored)
    acc = brief_domestic_route.format_accommodation_line(restored)
    assert "домик" in acc.lower() or "кухн" in acc.lower() or "уедин" in acc.lower()
    party = brief_display.format_party_group_summary(restored)
    assert brief_domestic_route.party_summary_redundant(restored, party)
    duration = brief_domestic_route.format_duration_display(restored)
    assert "≈14" in duration or "14 дн" in duration


def test_olga_without_flight_clarify():
    first = brief_parser.extract_brief_from_text(OLGA_FIRST, role="organizer")
    second = brief_parser.extract_brief_from_text(
        "Без визы, без перелётов.", role="organizer"
    )
    merged = brief_parser.merge_organizer_incoming(
        first, second, flow_step="organizer_clarify", has_prior_dump=True
    )
    assert merged.get("flight_not_needed") or merged.get("trip_transport") == "ground"
    missing = brief_parser.missing_brief_fields(merged)
    assert not any("Перелёт" in m for m in missing)
    assert not any("виз" in m.lower() for m in missing)


def test_olga_drive_hours_not_flight():
    base = brief_parser.extract_brief_from_text(OLGA_FIRST, role="organizer")
    clarify = brief_parser.extract_brief_from_text(
        "Без перелета. До 2 часов", role="organizer"
    )
    merged = brief_parser.merge_organizer_incoming(
        base,
        clarify,
        flow_step="organizer_clarify",
        has_prior_dump=True,
    )
    brief_parser._finalize_brief_from_text(
        merged, f"{OLGA_FIRST}\nБез перелета. До 2 часов"
    )
    assert merged.get("drive_hours_max") == 2
    assert not merged.get("flight_hours_max")
    display = format_transport_display(merged)
    assert "2" in display
    assert transport_field_label(merged) == "Передвижение"


def test_olga_budget_tyshch():
    brief = brief_parser.extract_brief_from_text("До 200 тыщ", role="organizer")
    assert brief.get("budget_rub_max") == 200_000


def test_gotovo_skips_parse():
    flat, structured = brief_parser.parse_message_to_brief("Готово", role="organizer")
    assert flat == {}
    assert structured == {}
