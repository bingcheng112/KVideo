"""爆款复刻：按内容画像清洗迁移脚本。"""
from __future__ import annotations

from app.services.viral_studio.content_profile import (
    ContentProfile,
    VoiceoverMode,
    is_placeholder_text,
    resolve_global_tone,
    strip_person_from_subject,
    strip_person_spatial,
)
from app.services.viral_studio.schemas import AdaptedScript, VideoDNA
from app.services.viral_studio.voice_delivery import refine_voice_delivery
from app.services.viral_studio.voice_delivery_rules import build_delivery_prompt


def _clear_voiceover_fields(scene) -> None:
    scene.new_voiceover = ""
    if scene.six:
        scene.six.audio.voiceover_semantic = ""
        scene.six.audio.voiceover_performed = ""
        scene.six.audio.tone_label = ""
        scene.six.audio.delivery_prompt = ""
        scene.six.audio.delivery = scene.six.audio.delivery.model_copy(
            update={
                "volume": "",
                "pace": "",
                "breath": "",
                "pause": "",
                "stress": "",
                "tail": "",
            }
        )


def _strip_person_from_scene(scene, profile: ContentProfile) -> None:
    if not scene.six:
        return
    six = scene.six
    if six.subject:
        six.subject = strip_person_from_subject(six.subject)
    six.spatial = strip_person_spatial(list(six.spatial or []))
    if profile.voiceover_mode != VoiceoverMode.ON_SCREEN:
        if six.audio.bgm and is_placeholder_text(six.audio.bgm):
            six.audio.bgm = ""


def _rebuild_delivery(scene, profile: ContentProfile, global_tone: str) -> None:
    if profile.voiceover_mode == VoiceoverMode.NONE:
        if scene.six:
            scene.six.audio.delivery_prompt = ""
        return
    performed = (scene.six.audio.voiceover_performed or "").strip()
    if not performed:
        return
    scene.six.audio.delivery_prompt = build_delivery_prompt(
        environment=scene.six.environment or "",
        shot_intent=scene.shot_intent or "",
        emotion=scene.six.audio.emotion or scene.emotion or "",
        tone_label=scene.six.audio.tone_label or global_tone or "",
        performed=performed,
        delivery=scene.six.audio.delivery.model_dump(),
        voiceover_mode=profile.voiceover_mode,
        requires_generic_person=profile.requires_generic_person,
        subject=scene.six.subject or "",
    )


def sanitize_adapted_script(
    script: AdaptedScript,
    video_dna: VideoDNA,
    profile: ContentProfile,
) -> AdaptedScript:
    """按内容画像就地清洗迁移脚本。"""
    gc = script.global_consistency
    global_tone = (gc.tone or "").strip()
    if is_placeholder_text(global_tone):
        resolved = resolve_global_tone(script, video_dna)
        gc.tone = resolved
        global_tone = resolved

    if is_placeholder_text(gc.character or "") and not profile.requires_generic_person:
        gc.character = ""
    if (
        profile.voiceover_mode != VoiceoverMode.ON_SCREEN
        and not profile.has_face_ref
        and not profile.requires_generic_person
    ):
        gc.character = ""

    for scene in script.adapted_script or []:
        if profile.voiceover_mode == VoiceoverMode.NONE:
            _clear_voiceover_fields(scene)
            _strip_person_from_scene(scene, profile)
        elif profile.voiceover_mode == VoiceoverMode.OFF_SCREEN:
            _strip_person_from_scene(scene, profile)
            refine_voice_delivery(
                scene,
                environment=scene.six.environment if scene.six else "",
                global_tone=global_tone,
                profile=profile,
            )
            _rebuild_delivery(scene, profile, global_tone)
        elif profile.requires_generic_person:
            if is_placeholder_text(scene.six.audio.bgm if scene.six else ""):
                scene.six.audio.bgm = ""
            refine_voice_delivery(
                scene,
                environment=scene.six.environment if scene.six else "",
                global_tone=global_tone,
                profile=profile,
            )
            _rebuild_delivery(scene, profile, global_tone)
        else:
            if is_placeholder_text(scene.six.audio.bgm if scene.six else ""):
                scene.six.audio.bgm = ""
            refine_voice_delivery(
                scene,
                environment=scene.six.environment if scene.six else "",
                global_tone=global_tone,
                profile=profile,
            )
            _rebuild_delivery(scene, profile, global_tone)

    return script
