import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_parser  # noqa: E402
import brief_stay_enrich  # noqa: E402


def test_bodrum_june_enriches_stay_and_closes_missing() -> None:
    text = (
        "семейная поездка в Турцию, Бодрум, 3 взрослых и 1 ребенок, "
        "13-23 июня, бюджет до 500к, прямой перелет, загранпаспорта есть"
    )
    brief = brief_parser.extract_brief_from_text(text)
    assert "Бодрум" in str(brief.get("stay_experience", {}).get("setting", []))
    assert brief.get("climate")
    assert "Сценарий отдыха" not in " ".join(brief_parser.missing_brief_fields(brief))


def test_boutique_mountains_from_text() -> None:
    text = "хочу премиальный бутик-отель в горах, Турция, июль"
    brief = brief_parser.extract_brief_from_text(text)
    se = brief.get("stay_experience") or {}
    acc = " ".join(se.get("accommodation_style") or []).lower()
    setting = " ".join(se.get("setting") or []).lower()
    assert "бутик" in acc or "премиум" in acc
    assert "гор" in setting or "гор" in acc


def test_turkey_month_without_city_still_sufficient() -> None:
    brief = {
        "activity_preferences": ["предпочтение по направлению: Турция"],
        "months": ["июн"],
        "context_raw": "Турция в июне",
    }
    brief_stay_enrich.enrich_stay_from_context(brief)
    assert brief_stay_enrich.stay_experience_sufficient(brief)
