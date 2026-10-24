"""Pass C：口播语言翻译（编译阶段，不改动 Pass B 脚本）。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException, status

from app.services.viral_studio.config_resolver import pick_plus_config
from app.services.viral_studio.copy_preserve import normalize_copy_text
from app.services.viral_studio.json_utils import parse_json_object
from app.services.viral_studio.omni_client import chat_completion_stream
from app.services.viral_studio.prompts.voiceover_translate import (
    VOICEOVER_TRANSLATE_SYSTEM,
    build_voiceover_translate_user_text,
)
from app.services.viral_studio.segment_merge import SegmentBundle
from app.services.viral_studio.voice_delivery_rules import build_delivery_prompt
from app.services.viral_studio.voiceover_languages import (
    VOICEOVER_LANGUAGE_EN,
    VOICEOVER_LANGUAGE_ZH,
    normalize_voiceover_language,
)

logger = logging.getLogger(__name__)

_USER_FRIENDLY_TRANSLATE_FAIL = "口播翻译失败，请稍后重试"
_USER_FRIENDLY_TRANSLATE_INEFFECTIVE = "口播翻译未生效，请重试或检查 qwen3.5-plus 配置"

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_CYRILLIC_RE = re.compile(r"[\u0400-\u04FF]")
_THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
_HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u30FF]")
_HANGUL_RE = re.compile(r"[\uAC00-\uD7AF\u1100-\u11FF]")

_SCRIPT_LANG_CHECKS: Dict[str, re.Pattern[str]] = {
    "ja": _HIRAGANA_KATAKANA_RE,
    "ko": _HANGUL_RE,
    "ar": _ARABIC_RE,
    "ru": _CYRILLIC_RE,
    "th": _THAI_RE,
}


def _voiceover_for_shot_bundle(shot) -> str:
    vo = (shot.voiceover_verbatim or "").strip()
    if vo:
        return vo
    audio = shot.six.audio
    return (audio.voiceover_performed or audio.voiceover_semantic or "").strip()


def snapshot_voiceover_sources(bundle: SegmentBundle) -> Dict[int, str]:
    """翻译前按镜号保存原文。"""
    out: Dict[int, str] = {}
    for i, shot in enumerate(bundle.sub_shots or []):
        src = _voiceover_for_shot_bundle(shot)
        if src:
            out[i] = src
    return out


def _looks_like_english(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if not _LATIN_RE.search(t):
        return False
    cjk = len(_CJK_RE.findall(t))
    return cjk / max(len(t), 1) < 0.3


def _looks_like_latin_without_cjk(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if not _LATIN_RE.search(t):
        return False
    cjk = len(_CJK_RE.findall(t))
    return cjk / max(len(t), 1) < 0.3


def _looks_like_target_language(text: str, lang: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if lang == VOICEOVER_LANGUAGE_EN:
        return _looks_like_english(t)
    script_re = _SCRIPT_LANG_CHECKS.get(lang)
    if script_re is not None:
        return bool(script_re.search(t))
    return _looks_like_latin_without_cjk(t)


def _resolve_translated_for_index(by_index: Dict[int, str], i: int) -> Tuple[str | None, bool]:
    """返回 (译文, 是否使用了 index+1 容错)。"""
    if i in by_index:
        return by_index[i], False
    if (i + 1) in by_index:
        return by_index[i + 1], True
    return None, False


def validate_translation_applied(
    bundle: SegmentBundle,
    sources: Dict[int, str],
    target_lang: str,
) -> None:
    """校验译文已生效；失败则抛 HTTPException。"""
    if not sources:
        return

    lang = normalize_voiceover_language(target_lang)
    passed = 0
    for i, original in sources.items():
        if i >= len(bundle.sub_shots or []):
            continue
        shot = bundle.sub_shots[i]
        translated = _voiceover_for_shot_bundle(shot)
        if not translated:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=_USER_FRIENDLY_TRANSLATE_INEFFECTIVE,
            )
        if normalize_copy_text(translated) == normalize_copy_text(original):
            continue
        if lang != VOICEOVER_LANGUAGE_ZH and not _looks_like_target_language(translated, lang):
            continue
        passed += 1

    if passed == 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_USER_FRIENDLY_TRANSLATE_INEFFECTIVE,
        )


def refresh_delivery_prompts_after_translate(
    bundle: SegmentBundle,
    target_lang: str,
) -> None:
    """翻译后重建各镜 delivery_prompt（非中文口播时避免【发声】仍嵌中文）。"""
    lang = normalize_voiceover_language(target_lang)
    if lang == VOICEOVER_LANGUAGE_ZH:
        return
    for shot in bundle.sub_shots or []:
        performed = _voiceover_for_shot_bundle(shot)
        if not performed:
            continue
        audio = shot.six.audio
        shot.six.audio.delivery_prompt = build_delivery_prompt(
            environment=shot.six.environment or "",
            shot_intent=shot.shot_intent or "",
            emotion=audio.emotion or shot.emotion or "",
            tone_label=audio.tone_label or "",
            performed=performed,
            delivery=audio.delivery.model_dump(),
            language=lang,
        )


def _build_shots_payload(bundle: SegmentBundle) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for i, shot in enumerate(bundle.sub_shots or []):
        payload.append(
            {
                "index": i,
                "start_sec": shot.start_sec,
                "end_sec": shot.end_sec,
                "beat_role": shot.beat_role,
                "voiceover": _voiceover_for_shot_bundle(shot),
            }
        )
    return payload


def apply_translations_to_bundle(
    bundle: SegmentBundle,
    translations: Dict[str, Any],
    *,
    target_lang: str = VOICEOVER_LANGUAGE_EN,
) -> SegmentBundle:
    """就地更新 bundle 口播字段；画面六要素不变。"""
    shots_out = translations.get("shots") or []
    by_index: Dict[int, str] = {}
    for item in shots_out:
        if not isinstance(item, dict):
            continue
        idx = item.get("index")
        if idx is None:
            continue
        by_index[int(idx)] = str(item.get("voiceover") or "").strip()

    for i, shot in enumerate(bundle.sub_shots or []):
        translated, off_by_one = _resolve_translated_for_index(by_index, i)
        if translated is None:
            continue
        if off_by_one:
            logger.warning(
                "口播翻译 index 容错 segment=%s shot=%s 使用 index+1",
                bundle.segment_index,
                i,
            )
        shot.voiceover_verbatim = translated
        shot.six.audio.voiceover_semantic = translated
        shot.six.audio.voiceover_performed = translated

    full_vo = str(translations.get("full_voiceover") or "").strip()
    if full_vo:
        bundle.full_voiceover_verbatim = full_vo
    elif bundle.sub_shots:
        parts = [_voiceover_for_shot_bundle(s) for s in bundle.sub_shots]
        parts = [p for p in parts if p]
        bundle.full_voiceover_verbatim = " ".join(parts)

    refresh_delivery_prompts_after_translate(bundle, target_lang)
    return bundle


async def translate_voiceover_bundle(
    user_id: str,
    bundle: SegmentBundle,
    target_lang: str,
) -> Tuple[SegmentBundle, int]:
    """
    将 bundle 内口播翻译为目标语言。
    target_lang=zh 时 no-op。
    """
    lang = normalize_voiceover_language(target_lang)
    if lang == VOICEOVER_LANGUAGE_ZH:
        return bundle, 0

    if not bundle.full_voiceover_verbatim and not any(
        _voiceover_for_shot_bundle(s) for s in (bundle.sub_shots or [])
    ):
        bundle.voiceover_language = lang
        return bundle, 0

    sources = snapshot_voiceover_sources(bundle)
    before_preview = (bundle.full_voiceover_verbatim or "")[:40]

    shots_payload = _build_shots_payload(bundle)
    shots_json = json.dumps(shots_payload, ensure_ascii=False, indent=2)

    try:
        _cfg, target_url, model_name = await pick_plus_config()
    except Exception as e:
        logger.warning("口播翻译：模型配置不可用: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="口播翻译模型未配置，请在管理后台启用 qwen3.5-plus",
        ) from e

    messages = [
        {"role": "system", "content": VOICEOVER_TRANSLATE_SYSTEM},
        {
            "role": "user",
            "content": build_voiceover_translate_user_text(
                target_language=lang,
                shots_json=shots_json,
                full_voiceover=bundle.full_voiceover_verbatim or "",
            ),
        },
    ]

    try:
        raw, _resp, cost, _bal = await chat_completion_stream(
            user_id,
            target_url=target_url,
            model_name=model_name,
            messages=messages,
            max_tokens=2048,
            video_seconds=0,
            consumption_remark="viral-studio-voiceover-translate",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("口播翻译 LLM 失败 segment=%s: %s", bundle.segment_index, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_USER_FRIENDLY_TRANSLATE_FAIL,
        ) from e

    try:
        data = parse_json_object(raw or "")
    except ValueError as e:
        logger.warning("口播翻译 JSON 解析失败 segment=%s: %s", bundle.segment_index, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_USER_FRIENDLY_TRANSLATE_FAIL,
        ) from e

    apply_translations_to_bundle(bundle, data, target_lang=lang)
    validate_translation_applied(bundle, sources, lang)
    bundle.voiceover_language = lang

    after_preview = (bundle.full_voiceover_verbatim or "")[:40]
    logger.info(
        "口播翻译 segment=%s lang=%s cost=%s before=%s after=%s",
        bundle.segment_index,
        lang,
        cost,
        before_preview,
        after_preview,
    )
    return bundle, int(cost or 0)
