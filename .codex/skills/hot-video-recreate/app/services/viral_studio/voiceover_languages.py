"""Pass C：口播语言常量与校验辅助。"""
from __future__ import annotations

VOICEOVER_LANGUAGE_ZH = "zh"
VOICEOVER_LANGUAGE_EN = "en"

# code -> LLM / lip-sync 提示用英文标签
VOICEOVER_LANGUAGE_OPTIONS: dict[str, str] = {
    "zh": "Chinese",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ru": "Russian",
    "sv": "Swedish",
    "th": "Thai",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "ms": "Malay",
    "fil": "Filipino",
    "ar": "Arabic",
    "tr": "Turkish",
    "ja": "Japanese",
    "ko": "Korean",
}

SUPPORTED_VOICEOVER_LANGUAGES = frozenset(VOICEOVER_LANGUAGE_OPTIONS.keys())


def normalize_voiceover_language(lang: str | None) -> str:
    key = (lang or "").strip().lower()
    if key in SUPPORTED_VOICEOVER_LANGUAGES:
        return key
    return VOICEOVER_LANGUAGE_ZH


def voiceover_language_label(lang: str | None) -> str:
    key = normalize_voiceover_language(lang)
    return VOICEOVER_LANGUAGE_OPTIONS.get(key, key)


def is_non_chinese_voiceover(lang: str | None) -> bool:
    return normalize_voiceover_language(lang) != VOICEOVER_LANGUAGE_ZH
