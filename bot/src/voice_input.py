"""Распознавание голосовых Telegram через OpenAI Whisper."""

from __future__ import annotations

import json
import logging
import os
import uuid
from io import BytesIO
from typing import Any, Optional

from env_util import env_flag


def voice_transcription_enabled() -> bool:
    if not env_flag("VOICE_TRANSCRIPTION_ENABLED", default="true"):
        return False
    return bool(os.getenv("LLM_API_KEY", "").strip())


async def transcribe_voice_message(
    bot: Any,
    voice: Any,
    *,
    language: Optional[str] = None,
) -> str:
    """
    Скачивает voice из Telegram и возвращает текст (Whisper).
    language — ISO 639-1 подсказка (ru, en, …).
    """
    if not voice_transcription_enabled():
        logging.warning("Voice transcription disabled or no LLM_API_KEY")
        return ""
    api_key = os.getenv("LLM_API_KEY", "").strip()
    file_id = getattr(voice, "file_id", None)
    if not file_id:
        return ""

    tg_file = await bot.get_file(file_id)
    if not tg_file or not tg_file.file_path:
        return ""

    buffer = BytesIO()
    await bot.download_file(tg_file.file_path, buffer)
    audio_bytes = buffer.getvalue()
    if not audio_bytes:
        return ""

    model = os.getenv("VOICE_WHISPER_MODEL", "whisper-1")
    return _whisper_transcribe(
        audio_bytes,
        filename="voice.ogg",
        api_key=api_key,
        model=model,
        language=language,
    )


def _whisper_transcribe(
    audio_bytes: bytes,
    *,
    filename: str,
    api_key: str,
    model: str,
    language: Optional[str],
) -> str:
    import urllib.error
    import urllib.request

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        parts.append(f"{value}\r\n".encode())

    add_field("model", model)
    if language:
        add_field("language", language[:2])
    add_field("response_format", "json")

    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
    )
    parts.append(b"Content-Type: application/octet-stream\r\n\r\n")
    parts.append(audio_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
        parsed = json.loads(raw)
        text = str(parsed.get("text") or "").strip()
        if text:
            logging.info("Voice transcribed (%d chars)", len(text))
        return text
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        KeyError,
        ValueError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ) as err:
        logging.warning("Whisper transcription failed: %s", err)
        return ""
