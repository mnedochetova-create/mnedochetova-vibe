import sys
from pathlib import Path


BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import parser_mode  # noqa: E402


def test_parser_mode_explicit(monkeypatch) -> None:
    monkeypatch.delenv("USE_STRUCTURED_BRIEF_PIPELINE", raising=False)
    monkeypatch.setenv("PARSER_MODE", "role_llm")
    assert parser_mode.get_parser_mode() == "role_llm"


def test_parser_mode_legacy_structured_flag(monkeypatch) -> None:
    monkeypatch.delenv("PARSER_MODE", raising=False)
    monkeypatch.setenv("USE_STRUCTURED_BRIEF_PIPELINE", "true")
    assert parser_mode.get_parser_mode() == "role_llm"


def test_parser_mode_default_rules(monkeypatch) -> None:
    monkeypatch.delenv("PARSER_MODE", raising=False)
    monkeypatch.setenv("USE_STRUCTURED_BRIEF_PIPELINE", "false")
    assert parser_mode.get_parser_mode() == "rules"
