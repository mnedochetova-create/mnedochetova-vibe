import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import brief_visibility


def test_parse_hide_budget_for_participants():
    text = "Участникам не показывай бюджет, турагенту оставлю сам"
    fields = brief_visibility.parse_visibility_fields_rules(text)
    assert "budget" in fields


def test_merge_hidden_fields():
    event = {}
    added = brief_visibility.merge_hidden_fields(event, ["budget", "dates"])
    assert "budget" in event["field_visibility"]["participant"]
    assert "dates" in event["field_visibility"]["share_plain"]
    assert set(added) == {"budget", "dates"}
