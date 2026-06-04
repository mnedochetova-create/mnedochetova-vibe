"""Rules-парсинг участника: не подставляем состав группы из общих фраз."""

import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_parser  # noqa: E402


def test_participant_rules_skip_group_adults() -> None:
    org = brief_parser.extract_brief_rule_based("2 взрослых, июль, бюджет 300к")
    part = brief_parser.extract_brief_rule_based("2 взрослых, июль, бюджет 300к", role="participant")
    assert org.get("adults") == 2
    assert "adults" not in part
    assert part.get("budget_rub_max") == 300_000


def test_participant_rules_keep_flight() -> None:
    text = "Перелёт до 4 часов, без пересадок"
    part = brief_parser.extract_brief_rule_based(text, role="participant")
    assert part.get("flight_hours_max") == 4
    assert part.get("transfers_allowed") is False
