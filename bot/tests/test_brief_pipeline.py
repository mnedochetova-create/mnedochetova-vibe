import sys
from pathlib import Path


BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_pipeline  # noqa: E402
import parser_mode  # noqa: E402


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


def test_transport_context_from_brief_multimodal() -> None:
    brief = {
        "trip_transport": "ground",
        "ground_transport_notes": ["на машине", "паром на остров"],
        "activity_preferences": ["пешком по Городцу", "пляж"],
        "flight_hours_max": None,
    }
    ctx = brief_pipeline.transport_context_from_brief(brief)
    assert ctx.get("trip_transport") == "ground"
    assert "на машине" in str(ctx.get("ground_transport_notes"))
    assert "пешком" in str(ctx.get("activity_preferences_transport"))


def test_build_organizer_user_prompt_includes_multimodal_hint() -> None:
    prompt = brief_pipeline.build_organizer_user_prompt(
        "Летим в Италию, дальше паром",
        brief_context={"ground_transport_notes": ["паром"]},
    )
    assert "мультимодальность" in prompt.lower() or "мультимодаль" in prompt.lower()
    assert "паром" in prompt
    assert "Летим в Италию" in prompt


def test_build_merger_user_prompt_wraps_payload() -> None:
    payload = {"flat_brief_json": {"trip_transport": "ground"}}
    prompt = brief_pipeline.build_merger_user_prompt(payload)
    assert "transport_mode_difference" in prompt
    assert "ground" in prompt


def test_role_llm_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("PARSER_MODE", "role_llm")
    monkeypatch.delenv("USE_STRUCTURED_BRIEF_PIPELINE", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert parser_mode.get_parser_mode() == "role_llm"
    assert parser_mode.role_llm_active() is False
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    assert parser_mode.role_llm_active() is True
