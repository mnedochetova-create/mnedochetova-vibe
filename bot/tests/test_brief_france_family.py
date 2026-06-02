import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_parser  # noqa: E402


FRANCE_FAMILY_TEXT = """
привет, мы едем большой семьей - брат с женой и ребенок 4 года, мои родители, муж, и свекровь брата
хотим поехать в середине июля на 10 дней на юг франции , есть загран паспорта
бюджет 15 000 евро
хочется совместить рестораны и пляжный отдых
""".strip()


def test_france_family_brief_by_meaning() -> None:
    brief = brief_parser.extract_brief_from_text(FRANCE_FAMILY_TEXT)
    missing = brief_parser.missing_brief_fields(brief)

    assert brief.get("budget_eur_max") == 15000
    assert brief.get("budget_currency") == "EUR"
    assert "budget_rub_max" not in brief or brief.get("budget_rub_max") != 15000
    assert brief.get("adults") == 6
    assert brief.get("kids_count") == 1
    assert brief.get("kid_age") == 4
    assert brief.get("date_range_raw")
    assert "июл" in (brief.get("months") or [""])[0]
    assert not any("разные мнения" in n for n in (brief.get("constraints_notes") or []))
    assert not any("Визы" in m for m in missing)
    assert not any("Кто едет" in m for m in missing)

    se = brief.get("stay_experience") or {}
    setting = " ".join(se.get("setting") or [])
    assert "Франция" in setting or "Юг Франции" in setting
    assert "море" in setting.lower() or "пляж" in setting.lower()


def test_passport_word_no_conflict_note() -> None:
    brief = brief_parser.extract_brief_from_text("загран паспорта есть, едем в отпуск")
    notes = " ".join(brief.get("constraints_notes") or [])
    assert "разные мнения" not in notes
