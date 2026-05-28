import sys
from pathlib import Path


BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_pipeline  # noqa: E402


def test_structured_pipeline_flag(monkeypatch) -> None:
    monkeypatch.setenv("USE_STRUCTURED_BRIEF_PIPELINE", "false")
    assert brief_pipeline.structured_pipeline_enabled() is False
    monkeypatch.setenv("USE_STRUCTURED_BRIEF_PIPELINE", "TRUE")
    assert brief_pipeline.structured_pipeline_enabled() is True


def test_upsert_participant_input_replaces_same_name() -> None:
    rows = [
        {"participant_name": "Maria", "personal_preferences": {"trip_type": {"value": "море"}}},
        {"participant_name": "Alex", "personal_preferences": {"trip_type": {"value": "горы"}}},
    ]
    new_row = {"participant_name": "Maria", "personal_constraints": {"flight_hours_max": {"value": 4}}}
    updated = brief_pipeline.upsert_participant_input(rows, new_row)
    assert len(updated) == 2
    maria = [row for row in updated if row.get("participant_name") == "Maria"][0]
    assert maria == new_row
