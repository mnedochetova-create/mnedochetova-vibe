"""Режим парсинга брифа: rules | role_llm."""

import os
from typing import Literal

from env_util import env_flag

ParserMode = Literal["rules", "role_llm"]

_VALID = frozenset({"rules", "role_llm"})


def get_parser_mode() -> ParserMode:
    explicit = (os.getenv("PARSER_MODE") or "").strip().lower()
    if explicit in _VALID:
        return explicit  # type: ignore[return-value]
    if env_flag("USE_STRUCTURED_BRIEF_PIPELINE"):
        return "role_llm"
    return "rules"


def llm_available() -> bool:
    return bool((os.getenv("LLM_API_KEY") or "").strip())


def role_llm_active() -> bool:
    return get_parser_mode() == "role_llm" and llm_available()
