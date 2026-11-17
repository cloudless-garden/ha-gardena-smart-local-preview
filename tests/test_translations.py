# SPDX-FileCopyrightText: 2026 GARDENA GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Tests that every translation file stays in sync with en.json.

A string that is not translated yet only produces a warning. Nobody speaks all
supported languages, and Home Assistant falls back to English for a missing
key. Keys that en.json does not know and wrong placeholders are bugs and fail.
"""

from __future__ import annotations

import json
import os
import re
import warnings
from pathlib import Path
from typing import Any

import pytest

TRANSLATIONS_DIR = (
    Path(__file__).parent.parent
    / "custom_components"
    / "gardena_smart_local_preview"
    / "translations"
)
PLACEHOLDER = re.compile(r"\{[^}]+\}")
# A GitHub annotation is limited in size, so a language that misses many
# strings lists only the first keys.
MAX_KEYS_IN_WARNING = 10

OTHER_LANGUAGES: list[str] = []
for _path in sorted(TRANSLATIONS_DIR.glob("*.json")):
    if _path.stem != "en":
        OTHER_LANGUAGES.append(_path.stem)


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat


def _load(language: str) -> dict[str, str]:
    path = TRANSLATIONS_DIR / f"{language}.json"
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


def test_other_languages_found() -> None:
    assert OTHER_LANGUAGES


@pytest.mark.parametrize("language", OTHER_LANGUAGES)
def test_no_keys_unknown_to_english(language: str) -> None:
    english = set(_load("en"))
    translated = set(_load(language))

    assert sorted(translated - english) == [], f"not in en.json: {language}.json"


@pytest.mark.parametrize("language", OTHER_LANGUAGES)
def test_report_missing_translations(
    language: str, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = sorted(set(_load("en")) - set(_load(language)))
    if not missing:
        return

    shown = ", ".join(missing[:MAX_KEYS_IN_WARNING])
    if len(missing) > MAX_KEYS_IN_WARNING:
        shown += f" and {len(missing) - MAX_KEYS_IN_WARNING} more"
    message = f"{language}.json misses {len(missing)} translations: {shown}"
    warnings.warn(message, stacklevel=1)
    if os.environ.get("GITHUB_ACTIONS"):
        # Pytest captures the output, but GitHub only turns a workflow command
        # at the start of a line of the live output into an annotation.
        with capsys.disabled():
            print(f"\n::warning title=Missing translation::{message}")


@pytest.mark.parametrize("language", OTHER_LANGUAGES)
def test_same_placeholders_as_english(language: str) -> None:
    english = _load("en")
    translated = _load(language)

    mismatches = []
    for key, english_text in english.items():
        if key not in translated:
            continue
        if sorted(PLACEHOLDER.findall(english_text)) != sorted(
            PLACEHOLDER.findall(translated[key])
        ):
            mismatches.append(key)

    assert mismatches == []
