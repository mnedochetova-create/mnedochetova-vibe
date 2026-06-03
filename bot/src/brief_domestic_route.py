"""Отображение и нормализация автопоездок по России (регионы, must-visit)."""

from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional

import brief_transport


def format_kids_count(count: int) -> str:
    return f"{count} {_kids_word(count)}"


def _kids_word(count: int) -> str:
    n = abs(int(count)) % 100
    n1 = n % 10
    if 11 <= n <= 14:
        return "детей"
    if n1 == 1:
        return "ребёнок"
    if 2 <= n1 <= 4:
        return "ребёнка"
    return "детей"


def parse_setting_tokens(raw_items: Any) -> List[str]:
    """Разобрать setting: отдельные области и строки вида \"['область', ...]\"."""
    if not raw_items:
        return []
    items = raw_items if isinstance(raw_items, list) else [raw_items]
    out: List[str] = []
    seen: set[str] = set()
    for raw in items:
        text = str(raw).strip()
        if not text:
            continue
        if text.startswith("[") and "]" in text:
            try:
                parsed = ast.literal_eval(text)
                if isinstance(parsed, list):
                    for part in parsed:
                        piece = str(part).strip()
                        if piece and piece not in seen:
                            seen.add(piece)
                            out.append(piece)
                    continue
            except (ValueError, SyntaxError):
                inner = text.strip("[]")
                for piece in re.split(r"['\"],\s*['\"]", inner):
                    piece = piece.strip(" '\"")
                    if piece and piece not in seen:
                        seen.add(piece)
                        out.append(piece)
                continue
        if text not in seen:
            seen.add(text)
            out.append(text)
    return out


def normalize_brief_stay_settings(brief: Dict[str, Any]) -> None:
    se = brief.get("stay_experience")
    if not isinstance(se, dict):
        return
    if se.get("setting") is not None:
        se["setting"] = parse_setting_tokens(se.get("setting"))
        brief["stay_experience"] = se
    if brief.get("regions"):
        brief["regions"] = parse_setting_tokens(brief["regions"])


def _raw_context_text(brief: Dict[str, Any]) -> str:
    parts: List[str] = []
    for key in ("organizer_dump", "context_raw"):
        val = brief.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val)
    return " ".join(parts)


def _search_text(brief: Dict[str, Any]) -> str:
    return _raw_context_text(brief).lower()


def _clean_date_range(raw: Optional[str]) -> str:
    text = str(raw or "").strip()
    text = re.sub(r"^в\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bпримерно\s+", "", text, flags=re.IGNORECASE)
    return text.strip()


def _extract_accommodation_phrase(text: str) -> str:
    """Фраза «Проживание в …» из текста организатора."""
    if not text.strip():
        return ""
    m = re.search(
        r"проживан\w*\s+(?:в|на)\s+([^.\n;]+)",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        phrase = m.group(1).strip()
        if len(phrase) > 8:
            return phrase[0].upper() + phrase[1:] if phrase else phrase
    return ""


def ensure_accommodation_from_context(brief: Dict[str, Any]) -> None:
    se = brief.get("stay_experience")
    if not isinstance(se, dict):
        se = {}
    acc = [str(a).strip() for a in (se.get("accommodation_style") or []) if str(a).strip()]
    if acc:
        return
    raw = _raw_context_text(brief)
    if not raw.strip():
        return
    phrase = _extract_accommodation_phrase(raw)
    if phrase:
        se["accommodation_style"] = [phrase]
        brief["stay_experience"] = se
        return
    blob = raw.lower()
    if re.search(r"домик|коттедж|гостев", blob) and re.search(
        r"кухн|уедин|необычн", blob
    ):
        labels: List[str] = []
        if "кухн" in blob:
            labels.append("домики с кухней")
        if "уедин" in blob or "необычн" in blob:
            labels.append("необычное уединённое размещение")
        if labels:
            se["accommodation_style"] = labels
            brief["stay_experience"] = se


def apply_domestic_cleanup(brief: Dict[str, Any]) -> None:
    """Убрать ложную «Москву» и мусор в setting при региональном туре."""
    normalize_brief_stay_settings(brief)
    regions = set(brief.get("regions") or [])
    se = brief.get("stay_experience")
    if not isinstance(se, dict):
        return
    setting = parse_setting_tokens(se.get("setting") or [])
    cleaned: List[str] = []
    for tag in setting:
        low = tag.lower()
        if tag in {"Москва", "москва"} or low == "экскурсии":
            continue
        if "област" in low or tag in regions:
            cleaned.append(tag)
            continue
        if tag in regions:
            cleaned.append(tag)
    for r in brief.get("regions") or []:
        if r not in cleaned:
            cleaned.append(r)
    if cleaned:
        se["setting"] = cleaned
        brief["stay_experience"] = se
    primary = brief.get("destination_primary")
    if primary and str(primary).strip().lower() in {"москва", "moscow"}:
        brief.pop("destination_primary", None)


def is_domestic_auto_brief(brief: Dict[str, Any]) -> bool:
    if brief.get("regions") or brief.get("must_visit_places"):
        return True
    se = brief.get("stay_experience") if isinstance(brief.get("stay_experience"), dict) else {}
    if any("област" in str(s).lower() for s in parse_setting_tokens(se.get("setting") or [])):
        return True
    trip = str(brief.get("trip_type") or "").lower()
    if "автопутешеств" in trip or "региональн" in trip:
        return True
    blob = _search_text(brief)
    if "област" in blob or re.search(r"центральн\w*\s+росси", blob):
        return True
    if brief.get("trip_transport") == brief_transport.TRIP_TRANSPORT_GROUND:
        if "росси" in blob or "путешеств" in blob:
            return True
    return False


def attach_event_context(brief: Dict[str, Any], event: Optional[Dict[str, Any]] = None) -> None:
    """Подтянуть organizer_dump/context с события, если в brief их нет."""
    if not event:
        return
    dump = event.get("organizer_dump")
    if isinstance(dump, str) and dump.strip() and not str(brief.get("organizer_dump") or "").strip():
        brief["organizer_dump"] = dump.strip()
    if not str(brief.get("context_raw") or "").strip():
        if isinstance(dump, str) and dump.strip():
            brief["context_raw"] = dump.strip()
        elif isinstance(event.get("context_raw"), str) and event["context_raw"].strip():
            brief["context_raw"] = event["context_raw"].strip()


def prepare_brief_for_display(
    brief: Dict[str, Any], *, event: Optional[Dict[str, Any]] = None
) -> None:
    """Перед карточкой: нормализация, domestic, проживание, заголовок."""
    if not brief:
        return
    attach_event_context(brief, event)
    normalize_brief_stay_settings(brief)
    if is_domestic_auto_brief(brief):
        apply_domestic_cleanup(brief)
        ensure_accommodation_from_context(brief)
        import brief_display

        brief_display.sync_trip_title(brief)
    elif not str(brief.get("trip_title") or "").strip():
        import brief_display

        brief_display.sync_trip_title(brief)


def format_dates_display(brief: Dict[str, Any]) -> str:
    if brief.get("date_range_raw"):
        return _clean_date_range(brief["date_range_raw"])
    months = brief.get("months") or []
    if months:
        return ", ".join(str(m) for m in months[:2])
    return ""


def format_duration_display(brief: Dict[str, Any]) -> str:
    explicit = brief.get("trip_duration_days_raw")
    if explicit:
        from brief_display import normalize_duration_display

        return normalize_duration_display(explicit)

    dr = format_dates_display(brief)
    m = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})", dr)
    if m:
        start, end = int(m.group(1)), int(m.group(2))
        if end >= start:
            days = end - start + 1
            return f"{dr} (≈{days} дн.)"
    return "—"


def _short_region_label(name: str) -> str:
    text = str(name).strip()
    if text.endswith("ая область"):
        return text[:- len("ая область")] + "ая обл."
    return text


def regions_short_list(regions: List[str]) -> str:
    labels = [_short_region_label(r) for r in regions if str(r).strip()]
    if not labels:
        return "центральной России"
    if len(labels) == 1:
        return labels[0]
    return f"{', '.join(labels[:-1])} и {labels[-1]}"


def format_domestic_scenario(brief: Dict[str, Any]) -> str:
    """Связный сценарий без «В ['область', ...]»."""
    regions = list(brief.get("regions") or [])
    se = brief.get("stay_experience") if isinstance(brief.get("stay_experience"), dict) else {}
    if not regions:
        regions = [
            s
            for s in parse_setting_tokens(se.get("setting") or [])
            if "област" in str(s).lower()
        ]

    period = format_dates_display(brief)
    reg_part = regions_short_list(regions)

    activity_bits: List[str] = []
    trip_type = str(brief.get("trip_type") or "").lower()
    if "экскурс" in trip_type or "автопутешеств" in trip_type:
        activity_bits.append("экскурсионный маршрут")
    elif trip_type:
        activity_bits.append(trip_type.split("/")[0])

    for item in brief.get("activity_preferences") or []:
        low = str(item).lower()
        if "достопримеч" in low or "максимум" in low:
            activity_bits.append("максимум впечатлений")
            break

    acc = [str(a) for a in (se.get("accommodation_style") or []) if str(a).strip()]
    if acc:
        activity_bits.append(", ".join(acc))

    head = f"Автопутешествие по {reg_part}"
    if period:
        head = f"{head}, {period}"
    if activity_bits:
        return f"{head} — {' · '.join(activity_bits)}."
    return f"{head}."


def derive_domestic_trip_title(brief: Dict[str, Any]) -> str:
    period = format_dates_display(brief)
    parts = ["Автопутешествие по центральной России"]
    if period:
        parts.append(period)
    adults = brief.get("adults")
    kids = brief.get("kids_count") or brief.get("kids")
    if isinstance(adults, int) and isinstance(kids, int) and kids > 0:
        parts.append(f"семья {adults}+{kids}")
    elif isinstance(adults, int) and adults == 2:
        parts.append("вдвоём")
    elif isinstance(adults, int) and adults >= 3:
        parts.append(f"компания {adults}")
    return " · ".join(parts)


def format_accommodation_line(brief: Dict[str, Any]) -> str:
    if is_domestic_auto_brief(brief):
        ensure_accommodation_from_context(brief)
    se = brief.get("stay_experience") if isinstance(brief.get("stay_experience"), dict) else {}
    acc = [str(a).strip() for a in (se.get("accommodation_style") or []) if str(a).strip()]
    if acc:
        return ", ".join(acc)
    for note in brief.get("constraints_notes") or []:
        low = str(note).lower()
        if "домик" in low or "кухн" in low or "уедин" in low:
            return str(note)
    return ""


def party_summary_redundant(brief: Dict[str, Any], summary: str) -> bool:
    """Скрыть «Группа», если повторяет состав без нюансов."""
    if not summary.strip():
        return True
    adults = brief.get("adults")
    kids = brief.get("kids_count")
    if not adults:
        return False
    low = summary.lower()
    if "взросл" not in low:
        return False
    if kids and not any(w in low for w in ("реб", "дет")):
        return False
    if re.search(r"большая семья:\s*\d+\s+взросл", low) and "—" not in summary:
        return True
    prefs = brief.get("party_preferences") or {}
    if not isinstance(prefs, dict) or not prefs:
        return True
    for data in prefs.values():
        if not isinstance(data, dict):
            continue
        if data.get("wants") or data.get("notes") or data.get("constraints"):
            return False
    return True
