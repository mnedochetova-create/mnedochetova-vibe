"""Общие маркеры pytest для bot/tests."""

import sys
from pathlib import Path

import pytest

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
TESTS_DIR = BOT_ROOT / "tests"
for path in (SRC_DIR, TESTS_DIR):
    entry = str(path)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "p1_retest: автоматический ретест P1 (зеркало P1_MANUAL_RETEST.md)",
    )
