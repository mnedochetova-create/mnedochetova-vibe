import sys
from pathlib import Path


BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import live_response  # noqa: E402


def test_live_responses_enabled_accepts_truthy_values(monkeypatch) -> None:
    for value in ("true", "TRUE", "yes", "1"):
        monkeypatch.setenv("USE_LLM_LIVE_RESPONSES", value)
        assert live_response.live_responses_enabled() is True
    monkeypatch.setenv("USE_LLM_LIVE_RESPONSES", "false")
    assert live_response.live_responses_enabled() is False


def test_generate_live_response_falls_back_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("USE_LLM_LIVE_RESPONSES", "false")
    result = live_response.generate_live_response(
        {"role": "organizer", "user_message": "test"},
        "fallback message",
    )
    assert result["assistant_text"] == "fallback message"
    assert result["source"] == "fallback_disabled"


def test_detect_field_changes_added_and_updated() -> None:
    before = {"budget_rub_max": 200000, "months": ["июль"]}
    incoming = {"budget_rub_max": 300000, "trip_type": "экскурсии/город"}
    after = {"budget_rub_max": 300000, "months": ["июль"], "trip_type": "экскурсии/город"}
    changes = live_response.detect_field_changes(before, incoming, after)
    assert "budget_rub_max" in changes["updated_fields"]
    assert "trip_type" in changes["added_fields"]
