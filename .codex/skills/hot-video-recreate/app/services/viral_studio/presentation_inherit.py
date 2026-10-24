"""呈现层继承后处理：补 generic 人物、纠正展示形态、对齐 beat_plan。"""
from __future__ import annotations

import re
from typing import List

from app.services.viral_studio.content_profile import ContentProfile, is_placeholder_text
from app.services.viral_studio.presentation_profile import (
    is_hanging_style,
    replace_hanging_phrases,
    should_inherit_handheld,
)
from app.services.viral_studio.schemas import (
    AdaptedScene,
    AdaptedScript,
    PresentationProfile,
    VideoDNA,
)
from app.services.viral_studio.six_elements import match_omni_entry
from app.services.viral_studio.source_term_sanitize import fix_cross_category_visual

_PERSON_TOKENS = ("博主", "手部模特", "模特", "主播", "出镜人物")
_HANDHELD_RE = re.compile(r"手持|举起|拿|握|旋转展示|举至|胸前", re.I)
_FACE_CONFLICT_RE = re.compile(r"无面部|不露脸|不露全脸|无脸|无五官", re.I)
_HAND_ONLY_CHAR_RE = re.compile(r"手部特写|手部出镜|仅手|only hand|implied", re.I)
_HANDHELD_DUP_RE = re.compile(r"(手持)+")


def _str(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _dna_action_for_entry(entry) -> str:
    if not entry:
        return ""
    parts: List[str] = []
    if entry.performance:
        parts.append(_str(entry.performance))
    vis = entry.visual or {}
    for subj in vis.get("subjects") or []:
        if isinstance(subj, dict) and subj.get("action"):
            parts.append(_str(subj["action"]))
    return " ".join(parts).strip()


def _should_force_generic_character(char: str, presentation: PresentationProfile) -> bool:
    if not char or is_placeholder_text(char):
        return True
    if presentation.mode == "on_screen_hand":
        return True
    if presentation.mode in ("on_screen_face", "on_screen_body") and _HAND_ONLY_CHAR_RE.search(char):
        return True
    if _FACE_CONFLICT_RE.search(char):
        return True
    return False


def _person_suffix_for_mode(mode: str) -> str:
    if mode == "on_screen_hand":
        return "手部模特"
    return "博主"


def _normalize_subject_person(subject: str, mode: str, product_ref: str = "参考图1") -> str:
    t = _str(subject)
    base = f"{product_ref}产品"
    if product_ref in t:
        m = re.search(rf"{re.escape(product_ref)}[^\+、，]*", t)
        if m:
            base = m.group(0).strip()
    suffix = _person_suffix_for_mode(mode)
    if mode == "on_screen_hand":
        return f"{base} + {suffix}"
    if any(tok in t for tok in _PERSON_TOKENS):
        return t
    return f"{base} + {suffix}"


def _polish_handheld_phrasing(text: str) -> str:
    if not text:
        return text
    t = text
    t = re.sub(r"手持挂有", "手持", t)
    t = re.sub(r"挂有", "拿着", t)
    t = _HANDHELD_DUP_RE.sub("手持", t)
    t = re.sub(r"手持展示手持", "手持展示", t)
    return t.strip()


def _scene_text_blob(scene: AdaptedScene) -> str:
    six = scene.six
    if not six:
        return scene.shot_intent or ""
    parts = [
        six.subject or "",
        six.motion or "",
        scene.shot_intent or "",
        six.audio.delivery_prompt or "",
        six.audio.voiceover_semantic or "",
        scene.new_voiceover or "",
        six.audio.voiceover_performed or "",
    ]
    parts.extend(six.spatial or [])
    return " ".join(p for p in parts if p)


def _scene_has_hanging(scene: AdaptedScene) -> bool:
    return is_hanging_style(_scene_text_blob(scene))


def _apply_hanging_replacements(text: str, product_ref: str = "参考图1") -> str:
    return _polish_handheld_phrasing(
        replace_hanging_phrases(text or "", product_ref=product_ref)
    )


def _apply_cross_category_to_scene(scene: AdaptedScene, inferred) -> None:
    if not scene.six:
        return
    six = scene.six
    for field in ("subject", "motion", "environment"):
        val = getattr(six, field, "") or ""
        if val:
            setattr(six, field, fix_cross_category_visual(val, inferred))
    six.spatial = [
        fix_cross_category_visual(s, inferred)
        for s in (six.spatial or [])
        if fix_cross_category_visual(s, inferred)
    ]
    if scene.shot_intent:
        scene.shot_intent = fix_cross_category_visual(scene.shot_intent, inferred)
    if scene.new_voiceover:
        scene.new_voiceover = fix_cross_category_visual(scene.new_voiceover, inferred)
    audio = six.audio
    for field in ("voiceover_semantic", "voiceover_performed", "delivery_prompt"):
        val = getattr(audio, field, "") or ""
        if val:
            setattr(audio, field, fix_cross_category_visual(val, inferred))


def _strip_photo_staging_fields(scene: AdaptedScene, product_ref: str) -> None:
    """清除产品参考图摄影陈列（衣架等）泄漏到 motion/spatial 等字段。"""
    if not scene.six:
        return
    six = scene.six
    for field in ("subject", "motion"):
        val = getattr(six, field, "") or ""
        if val:
            setattr(six, field, _apply_hanging_replacements(val, product_ref=product_ref))
    six.spatial = [
        _apply_hanging_replacements(s, product_ref=product_ref)
        for s in (six.spatial or [])
        if _apply_hanging_replacements(s, product_ref=product_ref)
    ]
    if scene.shot_intent:
        scene.shot_intent = _apply_hanging_replacements(scene.shot_intent, product_ref=product_ref)
    audio = six.audio
    for field in ("delivery_prompt", "voiceover_semantic", "voiceover_performed"):
        val = getattr(audio, field, "") or ""
        if val:
            setattr(audio, field, _apply_hanging_replacements(val, product_ref=product_ref))
    if scene.new_voiceover:
        scene.new_voiceover = _apply_hanging_replacements(scene.new_voiceover, product_ref=product_ref)
    cleaned_must: List[str] = []
    for item in scene.must_show or []:
        new = _apply_hanging_replacements(item, product_ref=product_ref)
        if new:
            cleaned_must.append(new)
    scene.must_show = cleaned_must


def _fix_hanging_to_handheld(
    scene: AdaptedScene,
    dna_action: str,
    presentation: PresentationProfile,
    *,
    product_ref: str = "参考图1",
) -> None:
    if not scene.six or not should_inherit_handheld(presentation):
        return
    six = scene.six
    if _scene_has_hanging(scene):
        handheld_motion = f"手持展示{product_ref}产品，自然旋转"
        if dna_action and _HANDHELD_RE.search(dna_action):
            candidate = fix_cross_category_visual(dna_action)
            if len(candidate) >= 8 and ("产品" in candidate or product_ref in candidate):
                handheld_motion = candidate
        motion = six.motion or ""
        if is_hanging_style(motion) and not _HANDHELD_RE.search(motion):
            six.motion = handheld_motion
    _strip_photo_staging_fields(scene, product_ref)


def _sync_beat_plan_display(
    script: AdaptedScript,
    presentation: PresentationProfile,
) -> None:
    if not script.beat_plan:
        return
    default_action = presentation.display_style or "产品展示"
    for bp in script.beat_plan:
        if not _str(bp.display_action):
            bp.display_action = default_action
        elif should_inherit_handheld(presentation) and is_hanging_style(bp.display_action):
            bp.display_action = replace_hanging_phrases(
                bp.display_action,
                replacement="手持展示",
                product_ref=(script.global_consistency.product_ref or "参考图1").strip() or "参考图1",
            )


def apply_presentation_inherit(
    script: AdaptedScript,
    video_dna: VideoDNA,
    presentation: PresentationProfile,
    profile: ContentProfile,
) -> AdaptedScript:
    """coherence 之后、sanitize 之前：继承原片呈现形态与 generic 人物。"""
    script.presentation_profile = presentation
    gc = script.global_consistency
    product_ref = (gc.product_ref or "参考图1").strip() or "参考图1"
    inferred = script.inferred_product

    if profile.requires_generic_person:
        char = _str(gc.character)
        if _should_force_generic_character(char, presentation):
            char = presentation.generic_character or "年轻博主，自然五官，非特定名人"
        gc = gc.model_copy(update={"character": char})
        script.global_consistency = gc

    mode = presentation.mode
    if mode in ("on_screen_face", "on_screen_hand", "on_screen_body"):
        for scene in script.adapted_script or []:
            if not scene.six:
                continue
            omni = match_omni_entry(
                video_dna,
                float(scene.start_sec or 0),
                float(scene.end_sec or 0),
            )
            dna_action = _dna_action_for_entry(omni)
            _fix_hanging_to_handheld(scene, dna_action, presentation, product_ref=product_ref)
            _apply_cross_category_to_scene(scene, inferred)
            scene.six.subject = _normalize_subject_person(
                scene.six.subject,
                mode,
                product_ref=product_ref,
            )

    _sync_beat_plan_display(script, presentation)
    return script
