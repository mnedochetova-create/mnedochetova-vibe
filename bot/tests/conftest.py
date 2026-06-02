"""Общие маркеры pytest для bot/tests."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "p1_retest: автоматический ретест P1 (зеркало P1_MANUAL_RETEST.md)",
    )
