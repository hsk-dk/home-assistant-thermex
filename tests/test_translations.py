"""Every language translates exactly what English does, with the same placeholders."""
import json
import re
from pathlib import Path

import pytest

TRANSLATIONS = Path(__file__).parent.parent / "custom_components" / "thermex_api" / "translations"
LANGUAGES = sorted(p.stem for p in TRANSLATIONS.glob("*.json") if p.stem != "en")


def load(language: str) -> dict:
    return json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8"))


def texts(node, path=""):
    """Yield (path, text) for every string in a translation file."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from texts(value, f"{path}/{key}")
    else:
        yield path, node


ENGLISH = dict(texts(load("en")))


def test_the_supported_languages():
    assert LANGUAGES == ["da", "de", "es", "fi", "no", "sv"]


@pytest.mark.parametrize("language", LANGUAGES)
def test_same_texts_as_english(language):
    translated = dict(texts(load(language)))

    assert set(translated) == set(ENGLISH)


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_text_is_empty_or_left_in_english_by_accident(language):
    translated = dict(texts(load(language)))

    assert all(isinstance(t, str) and t.strip() for t in translated.values())
    # Words that look the same in several languages ("Error", the brand) are fine,
    # but a whole sentence that is identical to the English one was not translated.
    untranslated = [p for p, t in translated.items() if t == ENGLISH[p] and len(t.split()) > 3]
    assert untranslated == []


@pytest.mark.parametrize("language", LANGUAGES)
def test_same_placeholders_as_english(language):
    translated = dict(texts(load(language)))

    for path, english in ENGLISH.items():
        assert set(re.findall(r"{(\w+)}", translated[path])) == set(re.findall(r"{(\w+)}", english)), path
