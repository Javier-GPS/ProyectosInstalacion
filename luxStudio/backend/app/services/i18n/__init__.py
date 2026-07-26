"""i18n helpers for the report-generation workflow.

Public surface:

- ``Language`` — the supported locale literal.
- ``SUPPORTED_LANGUAGES`` — set of valid Language values.
- ``normalize_language(language)`` — coerces an arbitrary input to a Language.
- ``translator(language)`` — returns a ``_t(key, **kwargs)`` closure that looks
  up the key in the requested language and falls back to English, then to the
  key itself. Use ``**kwargs`` for placeholder substitution (``{name}`` etc.).

The actual translation tables live in ``i18n.report``. When adding a new
sub-domain (e.g. email templates, CLI output), create ``i18n/<domain>.py``
with the same ``{es: {...}, en: {...}}`` shape and merge it into
``_MERGE`` below.
"""
from typing import Literal

from .report import REPORT_TRANSLATIONS

Language = Literal["es", "en", "fr", "pt", "de", "it"]
SUPPORTED_LANGUAGES = {"es", "en", "fr", "pt", "de", "it"}

_MERGE: list[dict[str, dict[str, str]]] = [REPORT_TRANSLATIONS]

TRANSLATIONS: dict[str, dict[str, str]] = {"es": {}, "en": {}, "fr": {}, "pt": {}, "de": {}, "it": {}}
for mod in _MERGE:
    for lang in ("es", "en", "fr", "pt", "de", "it"):
        TRANSLATIONS[lang].update(mod.get(lang, {}))


def normalize_language(language: str | None) -> Language:
    if language in SUPPORTED_LANGUAGES:
        return language  # type: ignore[return-value]
    return "es"


def translator(language: str | None):
    lang = normalize_language(language)

    def _t(key: str, **kwargs) -> str:
        value = TRANSLATIONS.get(lang, TRANSLATIONS["es"]).get(key) or TRANSLATIONS["en"].get(key) or key
        return value.format(**kwargs) if kwargs else value

    return _t


__all__ = ["Language", "SUPPORTED_LANGUAGES", "TRANSLATIONS", "normalize_language", "translator"]
