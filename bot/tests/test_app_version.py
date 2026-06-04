"""app_version: чтение VERSION и override BOT_UI_VERSION."""

import sys
from pathlib import Path

BOT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = BOT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import app_version  # noqa: E402


def test_resolve_reads_repo_version(monkeypatch) -> None:
    monkeypatch.delenv("BOT_UI_VERSION", raising=False)
    version = app_version.resolve_app_version()
    repo_version = (BOT_ROOT.parent / "VERSION").read_text(encoding="utf-8").strip()
    assert version == repo_version
    assert version.count(".") >= 2


def test_resolve_env_override(monkeypatch) -> None:
    monkeypatch.setenv("BOT_UI_VERSION", "9.9.9-test")
    assert app_version.resolve_app_version() == "9.9.9-test"
