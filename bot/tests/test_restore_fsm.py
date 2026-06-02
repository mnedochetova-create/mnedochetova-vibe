import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_parser  # noqa: E402


def test_restore_fsm_path_uses_dump_when_brief_empty() -> None:
    """Тот же вызов, что в restore_organizer_fsm_state после правки health-check."""
    dump = "2 взрослых, июль, бюджет 300к, Турция"
    event = {"organizer_dump": dump, "brief": {}}
    brief = brief_parser.restore_organizer_brief_from_event(event)
    assert brief.get("adults") == 2
    assert brief.get("budget_rub_max") == 300_000
    assert "июл" in (brief.get("months") or [])
