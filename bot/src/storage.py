import json
import logging
from pathlib import Path
from typing import Any, Dict


EVENTS_FILE = Path(__file__).resolve().parent.parent / "data" / "events.json"


def load_events_from_file() -> Dict[str, Dict[str, Any]]:
    try:
        if not EVENTS_FILE.exists():
            return {}
        raw = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        loaded: Dict[str, Dict[str, Any]] = {}
        for code, event in raw.items():
            row = dict(event or {})
            participants = row.get("participants") or {}
            participant_updates = row.get("participant_updates") or {}
            event_number = row.get("event_number")
            if isinstance(participants, list):
                participants = {
                    str(chat_id): {"role": "participant", "joined_at": row.get("created_at")}
                    for chat_id in participants
                }
            if isinstance(participant_updates, dict):
                participant_updates = {
                    str(chat_id): dict(payload or {})
                    for chat_id, payload in participant_updates.items()
                }
            row["participants"] = participants
            row["participant_updates"] = participant_updates
            if not isinstance(event_number, int):
                row["event_number"] = None
            loaded[code] = row

        numbered = [e.get("event_number") for e in loaded.values() if isinstance(e.get("event_number"), int)]
        current_max = max(numbered) if numbered else 0
        for event in loaded.values():
            if not isinstance(event.get("event_number"), int):
                current_max += 1
                event["event_number"] = current_max
        return loaded
    except Exception as err:
        logging.warning("Failed to load events from disk: %s", err)
        return {}


def save_events_to_file(events: Dict[str, Dict[str, Any]]) -> None:
    try:
        EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        EVENTS_FILE.write_text(
            json.dumps(events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as err:
        logging.warning("Failed to save events to disk: %s", err)
