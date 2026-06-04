import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import input_kind


def test_ack_emoji():
    assert input_kind.classify_input_kind("👍", brief_complete=False) == "ack"


def test_help_not_parsed_as_brief_on_dump():
    assert (
        input_kind.classify_input_kind(
            "Не знаю, что написать в бриф",
            role="organizer",
            flow_step="organizer_dump",
            brief_complete=False,
        )
        == "help"
    )


def test_supplement_only_when_complete():
    assert (
        input_kind.classify_input_kind(
            "Хочу дополнить",
            brief_complete=True,
        )
        == "supplement_request"
    )
    assert (
        input_kind.classify_input_kind(
            "Хочу дополнить",
            brief_complete=False,
        )
        != "supplement_request"
    )


def test_defer_message():
    assert (
        input_kind.classify_input_kind(
            "Пока так, ещё думаем",
            role="organizer",
            flow_step="organizer_clarify",
            brief_complete=False,
        )
        == "defer"
    )


def test_autofill_request():
    assert (
        input_kind.classify_input_kind(
            "Подбери сам и заполни бриф",
            role="organizer",
            flow_step="organizer_dump",
        )
        == "autofill_request"
    )


def test_share_visibility_request():
    assert (
        input_kind.classify_input_kind(
            "Участникам не показывай бюджет",
            role="organizer",
            flow_step="organizer_clarify",
        )
        == "share_visibility_request"
    )


def test_substantive_with_facts():
    text = "2 взрослых, июль, до 300к, Турция"
    assert (
        input_kind.classify_input_kind(
            text,
            role="organizer",
            flow_step="organizer_dump",
            brief_complete=False,
        )
        == "substantive"
    )
