"""Статус «Думаю» при обработке сообщений."""

import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import ui_feedback  # noqa: E402


def test_thinking_status_enabled_by_default() -> None:
    assert ui_feedback.THINKING_STATUS_ENABLED is True
    assert "Думаю" in ui_feedback.THINKING_STATUS_HTML
