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


# The wording of Thermex' own sites (thermex.dk/.no/.se/.fi/.es) for the decorative light, which
# is what the setup option for the Decolight is called in each language.
DECORATIVE_LIGHT = {
    "da": "dekorationslys",
    "no": "dekorasjonslys",
    "sv": "dekorationsljus",
    "fi": "tunnelmavalo",
    "es": "luz decorativa",
}


@pytest.mark.parametrize("language,term", sorted(DECORATIVE_LIGHT.items()))
def test_the_decolight_option_uses_the_word_on_thermexs_site(language, term):
    option = load(language)["config"]["step"]["user"]["data"]["enable_decolight"]

    assert term in option.lower()


# Mistakes that were found and fixed, so they do not come back.
MISTAKES = {
    "da": ["Enhætte", "password", "adgangskode"],  # typo for "Emhætte"; the app says "kodeord"
    "sv": ["filterbyte", "ljuss", "API lösenord", "Deco Light"],  # the filter is cleaned, not replaced
    "no": ["stemningslys"],
    "fi": ["tunnelmavalaistus"],
    "es": ["reinicio", "reiniciar", "luz ambiental"],
}


@pytest.mark.parametrize("language", sorted(MISTAKES))
def test_known_mistakes_stay_fixed(language):
    everything = " | ".join(text for _, text in texts(load(language))).lower()

    for mistake in MISTAKES[language]:
        assert mistake.lower() not in everything, mistake
