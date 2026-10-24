"""爆款复刻：真人露脸/出镜检测（偏严规则）。"""
from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple, Union

from app.services.viral_studio.content_profile import ContentProfile, VoiceoverMode
from app.services.viral_studio.schemas import AdaptedScript, VideoDNA

# 命中即 involves_real_person = True
_STRICT_HIT_PATTERNS: Tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"人脸",
        r"面容",
        r"五官",
        r"露脸",
        r"出镜",
        r"真人出镜",
        r"模特",
        r"主播",
        r"讲解者",
        r"人物参照",
        r"出镜人物",
        r"博主",
        r"男博主",
        r"女博主",
        r"手部模特",
        r"年轻博主",
        r"年轻女性博主",
        r"年轻男性博主",
        r"素人\s*vlog",
        r"人物：",
        r"face_ref",
        r"face\s*reference",
    )
)

# 否定约束短语（长句优先剥离，避免「无人物出镜」误触「出镜」）
_NEGATION_PHRASES: Tuple[str, ...] = (
    "口播为画外音旁白，画面中禁止出现人物、人脸、口型同步",
    "画面中禁止出现人物、人脸；无对白、无口型同步",
    "画面中禁止出现人物、人脸",
    "禁止出现人物、人脸",
    "无真人出镜",
    "无人物出镜",
    "无对白、无口型同步",
    "不出现人脸",
)

# 单独出现不触发（口播、手部、产品等）
_EXCLUDE_ONLY_PATTERNS: Tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"^口播$",
        r"^画外音$",
        r"^voiceover$",
        r"^手部$",
        r"^手指$",
        r"^产品$",
        r"^商品$",
    )
)


def _str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _strip_negation_phrases(text: str) -> str:
    t = _str(text)
    for phrase in _NEGATION_PHRASES:
        t = t.replace(phrase, "")
    return t


def _text_has_strict_hit(text: str) -> bool:
    t = _strip_negation_phrases(_str(text))
    if not t:
        return False
    for pat in _STRICT_HIT_PATTERNS:
        if pat.search(t):
            return True
    return False


def _collect_dna_texts(video_dna: Union[VideoDNA, dict, None]) -> List[str]:
    if video_dna is None:
        return []
    if isinstance(video_dna, VideoDNA):
        dna = video_dna
    else:
        try:
            dna = VideoDNA.model_validate(video_dna)
        except Exception:
            return []

    texts: List[str] = []
    for entry in dna.timeline or []:
        vis = entry.visual or {}
        for subj in vis.get("subjects") or []:
            if not isinstance(subj, dict):
                continue
            for key in ("desc", "action", "role"):
                val = _str(subj.get(key))
                if val:
                    texts.append(val)
    return texts


def _collect_script_texts(adapted_script: Union[AdaptedScript, dict, None]) -> List[str]:
    if adapted_script is None:
        return []
    if isinstance(adapted_script, AdaptedScript):
        script = adapted_script
    else:
        try:
            script = AdaptedScript.model_validate(adapted_script)
        except Exception:
            return []

    texts: List[str] = []
    gc = script.global_consistency
    if gc and gc.character:
        texts.append(gc.character)
    for scene in script.adapted_script or []:
        six = scene.six
        if six and six.subject:
            texts.append(six.subject)
    return texts


def detect_real_person_involvement(
    *,
    face_ref_index: int = 0,
    face_reference_image_url: str = "",
    video_dna: Union[VideoDNA, dict, None] = None,
    adapted_script: Union[AdaptedScript, dict, None] = None,
    segment_prompts: Optional[List[str]] = None,
    content_profile: Optional[ContentProfile] = None,
) -> Tuple[bool, str]:
    """
    偏严检测：仅明确人脸/出镜算真人；口播、手部不算。

    Returns:
        (involves_real_person, reason)
        reason: face_ref | content_profile | prompt_character | dna_subject | none
    """
    if int(face_ref_index or 0) > 0:
        return True, "face_ref"
    if _str(face_reference_image_url):
        return True, "face_ref"

    if content_profile is not None:
        if content_profile.has_face_ref:
            return True, "face_ref"
        if content_profile.requires_generic_person:
            script_texts = _collect_script_texts(adapted_script)
            for t in script_texts:
                if _text_has_strict_hit(t):
                    return True, "generic_person"
            for prompt in segment_prompts or []:
                if _text_has_strict_hit(_str(prompt)):
                    return True, "generic_person"
        if (
            not content_profile.has_on_screen_person
            and not content_profile.requires_generic_person
            and content_profile.voiceover_mode
            in (VoiceoverMode.NONE, VoiceoverMode.OFF_SCREEN)
        ):
            return False, "content_profile"

    dna_texts = _collect_dna_texts(video_dna)
    for t in dna_texts:
        if _text_has_strict_hit(t):
            return True, "dna_subject"

    script_texts = _collect_script_texts(adapted_script)
    for t in script_texts:
        if _text_has_strict_hit(t):
            return True, "prompt_character"

    for prompt in segment_prompts or []:
        if _text_has_strict_hit(_str(prompt)):
            return True, "prompt_character"

    return False, "none"
