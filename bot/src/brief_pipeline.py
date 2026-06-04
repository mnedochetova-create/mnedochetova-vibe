import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
ORGANIZER_PROMPT_FILE = PROMPTS_DIR / "brief_parser_organizer_system_prompt.md"
PARTICIPANT_PROMPT_FILE = PROMPTS_DIR / "brief_parser_participant_system_prompt.md"
MERGER_PROMPT_FILE = PROMPTS_DIR / "brief_merger_system_prompt.md"
ORGANIZER_USER_TEMPLATE_FILE = PROMPTS_DIR / "brief_parser_organizer_user_prompt_template.md"
PARTICIPANT_USER_TEMPLATE_FILE = PROMPTS_DIR / "brief_parser_participant_user_prompt_template.md"
MERGER_USER_TEMPLATE_FILE = PROMPTS_DIR / "brief_merger_user_prompt_template.md"

_ORGANIZER_PROMPT_CACHE: Optional[str] = None
_PARTICIPANT_PROMPT_CACHE: Optional[str] = None
_MERGER_PROMPT_CACHE: Optional[str] = None
_ORGANIZER_USER_TEMPLATE_CACHE: Optional[str] = None
_PARTICIPANT_USER_TEMPLATE_CACHE: Optional[str] = None
_MERGER_USER_TEMPLATE_CACHE: Optional[str] = None

_TRANSPORT_BRIEF_KEYS = (
    "trip_transport",
    "flight_hours_max",
    "flight_hours_unrestricted",
    "transfers_allowed",
    "flight_preferences",
    "flight_not_needed",
    "drive_hours_max",
    "ground_transport_notes",
)


def _load_prompt(path: Path, cache_value: Optional[str], label: str) -> str:
    if cache_value is not None:
        return cache_value
    try:
        return path.read_text(encoding="utf-8")
    except Exception as err:
        logging.warning("Failed to load %s prompt: %s", label, err)
        return ""


def get_organizer_prompt() -> str:
    global _ORGANIZER_PROMPT_CACHE
    _ORGANIZER_PROMPT_CACHE = _load_prompt(
        ORGANIZER_PROMPT_FILE, _ORGANIZER_PROMPT_CACHE, "organizer parser"
    )
    return _ORGANIZER_PROMPT_CACHE


def get_participant_prompt() -> str:
    global _PARTICIPANT_PROMPT_CACHE
    _PARTICIPANT_PROMPT_CACHE = _load_prompt(
        PARTICIPANT_PROMPT_FILE, _PARTICIPANT_PROMPT_CACHE, "participant parser"
    )
    return _PARTICIPANT_PROMPT_CACHE


def get_merger_prompt() -> str:
    global _MERGER_PROMPT_CACHE
    _MERGER_PROMPT_CACHE = _load_prompt(MERGER_PROMPT_FILE, _MERGER_PROMPT_CACHE, "brief merger")
    return _MERGER_PROMPT_CACHE


def get_organizer_user_template() -> str:
    global _ORGANIZER_USER_TEMPLATE_CACHE
    _ORGANIZER_USER_TEMPLATE_CACHE = _load_prompt(
        ORGANIZER_USER_TEMPLATE_FILE,
        _ORGANIZER_USER_TEMPLATE_CACHE,
        "organizer parser user",
    )
    return _ORGANIZER_USER_TEMPLATE_CACHE


def get_participant_user_template() -> str:
    global _PARTICIPANT_USER_TEMPLATE_CACHE
    _PARTICIPANT_USER_TEMPLATE_CACHE = _load_prompt(
        PARTICIPANT_USER_TEMPLATE_FILE,
        _PARTICIPANT_USER_TEMPLATE_CACHE,
        "participant parser user",
    )
    return _PARTICIPANT_USER_TEMPLATE_CACHE


def get_merger_user_template() -> str:
    global _MERGER_USER_TEMPLATE_CACHE
    _MERGER_USER_TEMPLATE_CACHE = _load_prompt(
        MERGER_USER_TEMPLATE_FILE,
        _MERGER_USER_TEMPLATE_CACHE,
        "brief merger user",
    )
    return _MERGER_USER_TEMPLATE_CACHE


def transport_context_from_brief(brief: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Срез полей передвижения для user prompt (мультимодальный контекст)."""
    if not isinstance(brief, dict) or not brief:
        return {}
    out: Dict[str, Any] = {}
    for key in _TRANSPORT_BRIEF_KEYS:
        val = brief.get(key)
        if val is None:
            continue
        if isinstance(val, list) and not val:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        out[key] = val
    prefs = brief.get("activity_preferences")
    if isinstance(prefs, list):
        transport_lines = [
            p
            for p in prefs
            if _activity_mentions_transport(str(p))
        ]
        if transport_lines:
            out["activity_preferences_transport"] = transport_lines[:8]
    return out


def _activity_mentions_transport(text: str) -> bool:
    low = text.lower()
    markers = (
        "перел",
        "авиа",
        "вылет",
        "машин",
        "авто",
        "поезд",
        "паром",
        "лодк",
        "яхт",
        "пеш",
        "трек",
        "автобус",
        "такси",
        "назем",
        "без перел",
    )
    return any(m in low for m in markers)


def _render_user_template(template: str, replacements: Dict[str, str]) -> str:
    if not template:
        return ""
    out = template
    for key, value in replacements.items():
        out = out.replace(key, value)
    return out


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def build_organizer_user_prompt(
    message_text: str,
    *,
    brief_context: Optional[Dict[str, Any]] = None,
) -> str:
    template = get_organizer_user_template()
    transport_ctx = transport_context_from_brief(brief_context)
    replacements = {
        "{{role}}": "organizer",
        "{{source}}": "organizer_message",
        "{{message_text}}": message_text or "",
        "{{transport_context_json}}": _as_json(transport_ctx) if transport_ctx else "{}",
    }
    rendered = _render_user_template(template, replacements)
    if rendered:
        return rendered
    return (
        "Контекст:\n"
        "role: organizer\n"
        "source: organizer_message\n"
        f"message_text: {message_text or ''}\n"
        f"transport_context: {_as_json(transport_ctx)}\n"
    )


def build_participant_user_prompt(
    message_text: str,
    participant_name: str,
    *,
    brief_context: Optional[Dict[str, Any]] = None,
) -> str:
    template = get_participant_user_template()
    transport_ctx = transport_context_from_brief(brief_context)
    replacements = {
        "{{role}}": "participant",
        "{{source}}": "participant_message",
        "{{participant_name}}": participant_name or "",
        "{{message_text}}": message_text or "",
        "{{transport_context_json}}": _as_json(transport_ctx) if transport_ctx else "{}",
    }
    rendered = _render_user_template(template, replacements)
    if rendered:
        return rendered
    return (
        "Контекст:\n"
        "role: participant\n"
        "source: participant_message\n"
        f"participant_name: {participant_name or ''}\n"
        f"message_text: {message_text or ''}\n"
        f"transport_context: {_as_json(transport_ctx)}\n"
    )


def build_merger_user_prompt(context_payload: Dict[str, Any]) -> str:
    template = get_merger_user_template()
    payload_json = json.dumps(context_payload, ensure_ascii=False, indent=2)
    replacements = {
        "{{merge_payload_json}}": payload_json,
    }
    rendered = _render_user_template(template, replacements)
    if rendered:
        return rendered
    return payload_json


def _call_json_llm(system_prompt: str, user_prompt: str) -> Dict[str, Any]:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key or not system_prompt or not user_prompt:
        return {}
    model = os.getenv("LLM_BRIEF_STRUCTURED_MODEL", os.getenv("LLM_PARSER_MODEL", "gpt-4o-mini"))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
        content = parsed["choices"][0]["message"]["content"]
        result = json.loads(content)
        return result if isinstance(result, dict) else {}
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        KeyError,
        ValueError,
        TimeoutError,
        OSError,
        IndexError,
        TypeError,
    ) as err:
        logging.warning("Structured brief pipeline LLM unavailable: %s", err)
        return {}


def parse_organizer_message(
    message_text: str,
    *,
    brief_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    user_prompt = build_organizer_user_prompt(
        message_text, brief_context=brief_context
    )
    return _call_json_llm(get_organizer_prompt(), user_prompt)


def parse_participant_message(
    message_text: str,
    participant_name: str,
    *,
    brief_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    user_prompt = build_participant_user_prompt(
        message_text,
        participant_name,
        brief_context=brief_context,
    )
    return _call_json_llm(get_participant_prompt(), user_prompt)


def merge_brief_inputs(
    *,
    flat_brief_json: Dict[str, Any],
    organizer_structured_history: List[Dict[str, Any]],
    organizer_structured_latest: Dict[str, Any],
    participant_inputs_json: List[Dict[str, Any]],
    new_participant_input_json: Dict[str, Any],
    current_event_status: str,
) -> Dict[str, Any]:
    merger_prompt = get_merger_prompt()
    context_payload = {
        "flat_brief_json": flat_brief_json or {},
        "organizer_structured_history": organizer_structured_history or [],
        "organizer_structured_latest": organizer_structured_latest or {},
        "participant_inputs_json": participant_inputs_json or [],
        "new_participant_input_json": new_participant_input_json or {},
        "current_event_status": current_event_status or "created",
    }
    user_prompt = build_merger_user_prompt(context_payload)
    return _call_json_llm(merger_prompt, user_prompt)


def upsert_participant_input(
    participant_inputs: List[Dict[str, Any]], new_input: Dict[str, Any]
) -> List[Dict[str, Any]]:
    if not isinstance(new_input, dict) or not new_input:
        return participant_inputs
    name = str(new_input.get("participant_name") or "").strip()
    if not name:
        return participant_inputs + [new_input]
    out: List[Dict[str, Any]] = []
    replaced = False
    for row in participant_inputs:
        row_name = str((row or {}).get("participant_name") or "").strip()
        if row_name == name and not replaced:
            out.append(new_input)
            replaced = True
        else:
            out.append(row)
    if not replaced:
        out.append(new_input)
    return out
