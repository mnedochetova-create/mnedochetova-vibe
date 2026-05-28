import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
LIVE_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "live_response_system_prompt.md"
LIVE_USER_TEMPLATE_FILE = PROMPTS_DIR / "live_response_user_prompt_template.md"

_SYSTEM_PROMPT_CACHE: Optional[str] = None
_USER_TEMPLATE_CACHE: Optional[str] = None

ALLOWED_TONES = {"neutral", "supportive", "concise"}


def live_responses_enabled() -> bool:
    return os.getenv("USE_LLM_LIVE_RESPONSES", "false").strip().lower() == "true"


def _load_prompt(path: Path, cache_value: Optional[str], label: str) -> str:
    if cache_value is not None:
        return cache_value
    try:
        return path.read_text(encoding="utf-8")
    except Exception as err:
        logging.warning("Failed to load %s prompt: %s", label, err)
        return ""


def get_live_system_prompt() -> str:
    global _SYSTEM_PROMPT_CACHE
    _SYSTEM_PROMPT_CACHE = _load_prompt(LIVE_SYSTEM_PROMPT_FILE, _SYSTEM_PROMPT_CACHE, "live system")
    return _SYSTEM_PROMPT_CACHE


def get_live_user_template() -> str:
    global _USER_TEMPLATE_CACHE
    _USER_TEMPLATE_CACHE = _load_prompt(LIVE_USER_TEMPLATE_FILE, _USER_TEMPLATE_CACHE, "live user")
    return _USER_TEMPLATE_CACHE


def _as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _build_user_prompt(context: Dict[str, Any]) -> str:
    template = get_live_user_template()
    if not template:
        return ""
    replacements = {
        "{{role}}": str(context.get("role", "organizer")),
        "{{flow_step}}": str(context.get("flow_step", "unknown")),
        "{{human_status}}": str(context.get("human_status", "none")),
        "{{allowed_next_action}}": str(context.get("allowed_next_action", "none")),
        "{{last_system_action}}": str(context.get("last_system_action", "none")),
        "{{brief_json}}": _as_json(context.get("brief_json", {})),
        "{{missing_fields_json}}": _as_json(context.get("missing_fields_json", [])),
        "{{parser_result_json}}": _as_json(context.get("parser_result_json", {})),
        "{{conflicts_json}}": _as_json(context.get("conflicts_json", [])),
        "{{recent_messages_json}}": _as_json(context.get("recent_messages_json", [])),
        "{{user_message}}": str(context.get("user_message", "")),
    }
    out = template
    for key, value in replacements.items():
        out = out.replace(key, value)
    return out


def _parse_live_response(content: str) -> Optional[Dict[str, Any]]:
    try:
        parsed = json.loads(content)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    text = parsed.get("assistant_text")
    tone = parsed.get("tone")
    confidence = parsed.get("confidence")
    if not isinstance(text, str) or not text.strip():
        return None
    if len(text) > 1200:
        text = text[:1200].rstrip()
    if tone not in ALLOWED_TONES:
        tone = "neutral"
    if not isinstance(confidence, (int, float)):
        confidence = 0.0
    confidence = max(0.0, min(1.0, float(confidence)))
    return {
        "assistant_text": text,
        "tone": tone,
        "confidence": confidence,
    }


def generate_live_response(context: Dict[str, Any], fallback_text: str) -> Dict[str, Any]:
    if not live_responses_enabled():
        return {
            "assistant_text": fallback_text,
            "tone": "neutral",
            "confidence": 1.0,
            "source": "fallback_disabled",
        }
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        return {
            "assistant_text": fallback_text,
            "tone": "neutral",
            "confidence": 1.0,
            "source": "fallback_no_key",
        }
    system_prompt = get_live_system_prompt()
    user_prompt = _build_user_prompt(context)
    if not system_prompt or not user_prompt:
        return {
            "assistant_text": fallback_text,
            "tone": "neutral",
            "confidence": 1.0,
            "source": "fallback_no_prompt",
        }

    model = os.getenv("LLM_LIVE_MODEL", os.getenv("LLM_PARSER_MODEL", "gpt-4o-mini"))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
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
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
        content = parsed["choices"][0]["message"]["content"]
        live = _parse_live_response(content)
        if not live:
            return {
                "assistant_text": fallback_text,
                "tone": "neutral",
                "confidence": 1.0,
                "source": "fallback_invalid_json",
            }
        return {**live, "source": "llm"}
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
        logging.warning("Live response LLM unavailable, fallback to static text: %s", err)
        return {
            "assistant_text": fallback_text,
            "tone": "neutral",
            "confidence": 1.0,
            "source": "fallback_error",
        }


def build_parser_result(
    *,
    saved: bool,
    confidence: float,
    added_fields: Optional[List[str]] = None,
    updated_fields: Optional[List[str]] = None,
    unclear_items: Optional[List[str]] = None,
    conflicts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return {
        "saved": bool(saved),
        "confidence": max(0.0, min(1.0, float(confidence))),
        "added_fields": added_fields or [],
        "updated_fields": updated_fields or [],
        "unclear_items": unclear_items or [],
        "conflicts": conflicts or [],
    }


def detect_field_changes(
    before: Dict[str, Any],
    incoming: Dict[str, Any],
    after: Dict[str, Any],
) -> Dict[str, List[str]]:
    added: List[str] = []
    updated: List[str] = []
    for key in incoming.keys():
        if key not in after:
            continue
        if key not in before:
            added.append(key)
        elif before.get(key) != after.get(key):
            updated.append(key)
    return {"added_fields": added, "updated_fields": updated}
