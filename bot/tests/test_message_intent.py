import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import message_intent


def test_brief_input_with_travel_facts():
    text = "2 взрослых, 1 ребенок, бюджет до 250к, Греция, конец августа, море"
    assert (
        message_intent.classify_message_intent(text, role="organizer", flow_step="organizer_dump")
        == "brief_input"
    )


def test_conversation_question():
    text = "Что мне написать в бриф? Не понимаю"
    assert (
        message_intent.classify_message_intent(text, role="organizer", flow_step="organizer_clarify")
        == "conversation"
    )


def test_mixed_when_question_and_facts_balanced() -> None:
    text = "Помоги сформулировать: 2 взрослых, июль, не знаю бюджет"
    assert message_intent.classify_message_intent(
        text, role="organizer", flow_step="organizer_clarify"
    ) in {"mixed", "conversation", "brief_input"}


def test_question_with_many_facts_is_brief() -> None:
    text = "Подскажи: 2 взрослых, июль, Турция, до 300к, без пересадок, море?"
    assert (
        message_intent.classify_message_intent(text, role="organizer", flow_step="organizer_dump")
        == "brief_input"
    )


def test_has_substantive_parsed_fields():
    assert message_intent.has_substantive_parsed_fields({"context_raw": "hello"}) is False
    assert message_intent.has_substantive_parsed_fields({"budget": "250k"}) is True
