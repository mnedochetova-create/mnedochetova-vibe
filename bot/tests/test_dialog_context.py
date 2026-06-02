import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import dialog_context


def test_dialog_history_trim_and_summary() -> None:
    history = [
        {"role": "user", "text": "Привет"},
        {"role": "assistant", "text": "Здравствуй"},
        {"role": "user", "text": "Что писать в бриф?"},
    ]
    trimmed = dialog_context.trim_dialog_history(history)
    assert len(trimmed) == 3
    assert "Привет" in dialog_context.build_dialog_summary(trimmed)
    assert dialog_context.last_bot_message(trimmed) == "Здравствуй"


def test_brief_insight_line() -> None:
    brief = {
        "adults": 2,
        "kids_count": 1,
        "activity_preferences": ["предпочтение по направлению: Греция"],
        "budget_rub_max": 250_000,
        "months": ["август"],
    }
    insight = dialog_context.brief_insight_line(brief)
    assert "Греция" in insight
    assert "250" in insight


def test_prioritize_missing() -> None:
    missing = ["a", "b", "c", "d"]
    assert dialog_context.prioritize_missing(missing, limit=2) == ["a", "b"]
