"""Shared test helpers."""

import json
from pathlib import Path

_THEMES = json.loads(
    (Path(__file__).parent.parent / "data" / "themes.json").read_text()
)


def classic_theme() -> dict:
    return _THEMES["classic"]


def modern_theme() -> dict:
    return _THEMES["modern"]


def print_theme() -> dict:
    return _THEMES["print"]
