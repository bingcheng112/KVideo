"""Pass B2：配音真实感排版（符号 → 六维发声 → 场景包裹）。"""
from __future__ import annotations

from typing import Optional

from app.services.viral_studio.content_profile import ContentProfile, VoiceoverMode
from app.services.viral_studio.schemas import AdaptedScene, VoiceDeliverySix
from app.services.viral_studio.voice_delivery_rules import (
    EMOTION_DELIVERY_PRESETS,
    apply_symbol_punctuation,
    build_delivery_prompt,
    normalize_semantic,
    resolve_emotion_key,
)


def _fill_delivery(emotion: str, tone_label: str) -> VoiceDeliverySix:
    key = resolve_emotion_key(emotion)
    preset = EMOTION_DELIVERY_PRESETS.get(key, EMOTION_DELIVERY_PRESETS["calm"])
    return VoiceDeliverySix(
        volume=preset.get("volume", ""),
        pace=preset.get("pace", ""),
        breath=preset.get("breath", ""),
        pause=preset.get("pause", ""),
        stress=preset.get("stress", ""),
        tail=preset.get("tail", ""),
    )


def refine_voice_delivery(
    scene: AdaptedScene,
    *,
    environment: str = "",
    global_tone: str = "",
    profile: Optional[ContentProfile] = None,
) -> AdaptedScene:
    """
    三步排版（纯规则）：
    1. semantic → performed
    2. emotion → delivery 六维
    3. 场景包裹 → delivery_prompt
    """
    mode = profile.voiceover_mode if profile else VoiceoverMode.ON_SCREEN
    six = scene.six
    audio = six.audio

    semantic = (audio.voiceover_semantic or scene.new_voiceover or "").strip()
    emotion = (audio.emotion or scene.emotion or "").strip()
    tone_label = (audio.tone_label or global_tone or "").strip()
    env = (environment or six.environment or "").strip()

    if mode == VoiceoverMode.NONE:
        audio.voiceover_semantic = ""
        audio.voiceover_performed = ""
        audio.tone_label = ""
        audio.delivery_prompt = ""
        six.audio = audio
        scene.six = six
        scene.new_voiceover = ""
        return scene

    if semantic and not audio.voiceover_semantic:
        audio.voiceover_semantic = semantic

    performed = (audio.voiceover_performed or "").strip()
    if not performed and semantic:
        performed = apply_symbol_punctuation(semantic, emotion)
        audio.voiceover_performed = performed
    elif performed and semantic:
        if not audio.voiceover_semantic:
            audio.voiceover_semantic = semantic

    if not audio.emotion and emotion:
        audio.emotion = emotion

    if not audio.tone_label and tone_label:
        audio.tone_label = tone_label

    if not any(
        [
            audio.delivery.volume,
            audio.delivery.pace,
            audio.delivery.breath,
        ]
    ):
        audio.delivery = _fill_delivery(emotion, tone_label)

    if not audio.delivery_prompt and performed:
        audio.delivery_prompt = build_delivery_prompt(
            environment=env,
            shot_intent=scene.shot_intent or "",
            emotion=emotion,
            tone_label=tone_label,
            performed=performed,
            delivery=audio.delivery.model_dump(),
            voiceover_mode=mode,
            requires_generic_person=profile.requires_generic_person if profile else False,
            subject=six.subject or "",
        )

    six.audio = audio
    scene.six = six
    scene.new_voiceover = semantic
    return scene


def semantic_preserved(semantic: str, performed: str) -> bool:
    """校验 performed 未改语义。"""
    return normalize_semantic(semantic) == normalize_semantic(performed)
