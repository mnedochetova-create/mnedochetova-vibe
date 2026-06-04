"""brief_merger: payload и применение результата без изменения brief."""

import brief_merger


def test_append_organizer_structured_history() -> None:
    event: dict = {}
    s1 = {"role": "organizer", "facts": {"adults": {"value": 2}}}
    s2 = {"role": "organizer", "facts": {"budget_rub_max": {"value": 300000}}}
    brief_merger.append_organizer_structured(event, s1)
    brief_merger.append_organizer_structured(event, s2)
    assert len(event["organizer_structured_history"]) == 2
    assert event["base_brief_structured"] == s2


def test_build_merger_payload_includes_flat_brief() -> None:
    event = {
        "brief": {"adults": 2, "budget_rub_max": 250000},
        "organizer_structured_history": [{"a": 1}],
        "base_brief_structured": {"b": 2},
        "participant_inputs_structured": [{"participant_name": "Ann", "context_raw": "до 4 ч"}],
    }
    payload = brief_merger.build_merger_payload(
        event,
        new_participant_input_json={"participant_name": "Ann"},
        current_event_status="active",
    )
    assert payload["flat_brief_json"]["adults"] == 2
    assert len(payload["organizer_structured_history"]) >= 1
    assert payload["new_participant_input_json"]["participant_name"] == "Ann"


def test_apply_merger_result_does_not_touch_brief() -> None:
    event = {"brief": {"adults": 2}}
    merged = {
        "conflicts": [
            {
                "issue_type": "preference_difference",
                "topic": "перелёт",
                "description": "разные лимиты часов",
            }
        ],
        "open_questions": ["Уточнить лимит перелёта у всех"],
        "organizer_update_text": "Участник Ann: перелёт до 4 ч.",
        "merged_brief": {"adults": 99},
    }
    conflicts, questions = brief_merger.apply_merger_result(event, merged)
    assert event["brief"]["adults"] == 2
    assert len(conflicts) == 1
    assert questions == ["Уточнить лимит перелёта у всех"]
    assert event["merger_pending_update_text"] == "Участник Ann: перелёт до 4 ч."
    assert event["merger_result_structured"] == merged


def test_open_questions_from_merger_objects() -> None:
    merged = {"open_questions": [{"question": "Когда вылет?"}]}
    assert brief_merger.open_questions_from_merger(merged) == ["Когда вылет?"]
