import sys
from pathlib import Path


BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import brief_flat_mapper  # noqa: E402


def test_organizer_structured_to_flat_core_fields() -> None:
    structured = {
        "context_raw": "2 взрослых, август, бюджет 300к",
        "facts": {
            "adults": {"value": 2, "confidence": "high"},
            "budget_rub_max": {"value": 300000, "confidence": "high"},
            "months": {"value": ["август"], "confidence": "high"},
            "destination": {"value": "Греция", "confidence": "medium"},
        },
        "constraints": {
            "flight_hours_max": {"value": 5, "confidence": "high"},
            "visa_required": {"value": False, "confidence": "high"},
        },
        "preferences": {
            "climate": {"value": "море/пляж", "confidence": "high"},
        },
    }
    flat = brief_flat_mapper.organizer_structured_to_flat(structured)
    assert flat["adults"] == 2
    assert flat["budget_rub_max"] == 300000
    assert flat["months"] == ["август"]
    assert flat["flight_hours_max"] == 5
    assert flat["visa_required"] is False
    assert flat["climate"] == "море/пляж"
    assert any("Греция" in item for item in flat.get("activity_preferences", []))


def test_conflicts_from_merger() -> None:
    merged = {
        "conflicts": [
            {
                "issue_type": "preference_difference",
                "topic": "Климат",
                "description": "Организатор — море, участник — горы",
            }
        ]
    }
    lines = brief_flat_mapper.conflicts_from_merger(merged)
    assert len(lines) == 1
    assert "Климат" in lines[0]
