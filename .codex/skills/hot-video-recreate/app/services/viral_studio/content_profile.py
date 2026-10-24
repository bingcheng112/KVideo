"""爆款复刻：内容画像（纯视觉 / 画外音 / 出镜口播）。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Union

from app.services.viral_studio.presentation_profile import (
    extract_presentation_profile,
    presentation_has_person,
    requires_generic_person,
)
from app.services.viral_studio.schemas import AdaptedScript, PresentationProfile, VideoDNA

PLACEHOLDER_TEXTS = frozenset(
    {
        "全片统一人物描述",
        "继承 DNA 全片语气",
        "继承 DNA voiceover.tone",
        "继承原片语气",
        "背景音乐风格与变化",
    }
)

_PERSON_SUBJECT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"人脸",
        r"面容",
        r"五官",
        r"露脸",
        r"出镜",
        r"真人",
        r"模特",
        r"主播",
        r"博主",
        r"讲解者",
        r"素人\s*vlog",
        r"^host$",
    )
)

_NARRATOR_ONLY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"^narrator$",
        r"^画外音$",
        r"^旁白$",
        r"^voiceover$",
    )
)

_HAND_ONLY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"手部",
        r"手指",
        r"^手$",
        r"手持",
        r"举起",
    )
)

_PERSON_PERFORMANCE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"惊讶",
        r"讲解",
        r"闲聊",
        r"表情",
        r"口播",
        r"对镜",
        r"出镜",
    )
)

_PERSON_SPATIAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"人物居",
        r"博主",
        r"主播",
        r"人脸",
        r"出镜",
    )
)


class VoiceoverMode(str, Enum):
    NONE = "none"
    OFF_SCREEN = "off_screen"
    ON_SCREEN = "on_screen"


@dataclass(frozen=True)
class ContentProfile:
    has_voiceover: bool
    has_on_screen_person: bool
    voiceover_mode: VoiceoverMode
    has_face_ref: bool
    requires_generic_person: bool = False
    presentation_mode: str = "none"


def is_placeholder_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t in PLACEHOLDER_TEXTS:
        return True
    return any(p in t for p in PLACEHOLDER_TEXTS if len(p) > 4)


def _str(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _text_has_person_signal(text: str) -> bool:
    t = _str(text)
    if not t:
        return False
    for pat in _NARRATOR_ONLY_PATTERNS:
        if pat.search(t):
            return False
    for pat in _HAND_ONLY_PATTERNS:
        if pat.search(t):
            return True
    for pat in _PERSON_SUBJECT_PATTERNS:
        if pat.search(t):
            return True
    return False


def is_person_spatial_line(line: str) -> bool:
    t = _str(line)
    if not t:
        return False
    return any(pat.search(t) for pat in _PERSON_SPATIAL_PATTERNS)


def strip_person_from_subject(subject: str) -> str:
    t = _str(subject)
    if not t:
        return ""
    for sep in (" + 博主", "+博主", " +博主", "+ 博主", "、博主", "，博主"):
        if sep in t:
            t = t.split(sep)[0].strip()
    for token in ("博主", "男博主", "女博主", "主播", "模特", "出镜人物"):
        t = re.sub(rf"[\s\+、，]*{re.escape(token)}", "", t)
    t = re.sub(r"\s+", " ", t).strip(" +、，")
    return t


def strip_person_spatial(spatial: List[str]) -> List[str]:
    out: List[str] = []
    for line in spatial or []:
        s = _str(line)
        if s and not is_person_spatial_line(s):
            out.append(s)
    return out


def dna_has_voiceover(dna: Union[VideoDNA, None]) -> bool:
    if dna is None:
        return False
    for entry in dna.timeline or []:
        audio = entry.audio
        if audio and audio.voiceover and _str(audio.voiceover.text):
            return True
    return False


def dna_has_presentation_person(dna: Union[VideoDNA, None]) -> bool:
    """含手部/身体出镜的呈现人物信号。"""
    if dna is None:
        return False
    presentation = extract_presentation_profile(dna)
    return presentation_has_person(presentation)


def dna_has_on_screen_person(dna: Union[VideoDNA, None]) -> bool:
    if dna is None:
        return False
    for entry in dna.timeline or []:
        if _text_has_person_signal(entry.performance):
            return True
        vis = entry.visual or {}
        for subj in vis.get("subjects") or []:
            if not isinstance(subj, dict):
                continue
            role = _str(subj.get("role") or subj.get("id"))
            if role and any(
                pat.search(role)
                for pat in _PERSON_SUBJECT_PATTERNS
                if not any(n.search(role) for n in _NARRATOR_ONLY_PATTERNS)
            ):
                if not any(n.search(role) for n in _NARRATOR_ONLY_PATTERNS):
                    return True
            for key in ("desc", "action"):
                if _text_has_person_signal(subj.get(key)):
                    return True
        spatial = entry.spatial or {}
        relations = spatial.get("relations") if isinstance(spatial, dict) else spatial
        if isinstance(relations, list):
            for rel in relations:
                if is_person_spatial_line(_str(rel)):
                    return True
        elif isinstance(relations, str) and is_person_spatial_line(relations):
            return True
    return False


def build_content_profile(
    dna: Union[VideoDNA, None],
    *,
    face_ref_index: int = 0,
    character_summary: str = "",
    presented_gender: str = "",
    presentation: Union[PresentationProfile, None] = None,
) -> ContentProfile:
    pg = (presented_gender or "").strip().lower()
    has_face_ref = int(face_ref_index or 0) > 0 or bool(_str(character_summary)) or pg in (
        "female",
        "male",
    )
    has_voiceover = dna_has_voiceover(dna)
    pres = presentation or (extract_presentation_profile(dna) if dna else None)
    has_presentation = (
        presentation_has_person(pres) if pres else dna_has_presentation_person(dna)
    )
    has_person = has_face_ref or has_presentation or dna_has_on_screen_person(dna)
    needs_generic = (
        requires_generic_person(pres, has_face_ref=has_face_ref)
        if pres
        else (has_presentation and not has_face_ref)
    )

    if not has_voiceover:
        mode = VoiceoverMode.NONE
    elif has_person:
        mode = VoiceoverMode.ON_SCREEN
    else:
        mode = VoiceoverMode.OFF_SCREEN

    return ContentProfile(
        has_voiceover=has_voiceover,
        has_on_screen_person=has_person,
        voiceover_mode=mode,
        has_face_ref=has_face_ref,
        requires_generic_person=needs_generic,
        presentation_mode=pres.mode if pres else "none",
    )


def resolve_global_tone(script: AdaptedScript, video_dna: Union[VideoDNA, None]) -> str:
    """解析有效全片语气，跳过 Pass B 占位符。"""
    gc_tone = _str(script.global_consistency.tone if script.global_consistency else "")
    if gc_tone and not is_placeholder_text(gc_tone):
        return gc_tone

    if video_dna:
        for entry in video_dna.timeline or []:
            audio = entry.audio
            if not audio or not audio.voiceover:
                continue
            dna_tone = _str(audio.voiceover.tone)
            if dna_tone and not is_placeholder_text(dna_tone):
                return dna_tone

    for scene in script.adapted_script or []:
        if not scene.six:
            continue
        tl = _str(scene.six.audio.tone_label)
        if tl and not is_placeholder_text(tl):
            return tl
        break
    return ""


def theme_line_for_profile(profile: ContentProfile, genre: str, tone: str) -> str:
    g = (genre or "").strip() or "短视频"
    t = (tone or "").strip()
    effective = t if t and not is_placeholder_text(t) else ""
    if profile.voiceover_mode == VoiceoverMode.NONE:
        base = f"{g}，纯视觉产品展示，无人物出镜，无对白"
    elif profile.voiceover_mode == VoiceoverMode.OFF_SCREEN:
        base = f"{g}，画外音旁白+产品画面，无人物出镜"
        if effective:
            base += f"，{effective}"
    else:
        base = f"{g}，{effective}" if effective else g
    return f"{base}，手机实拍感，超写实。"


def constraint_suffix_for_profile(profile: ContentProfile) -> str:
    if profile.requires_generic_person and not profile.has_face_ref:
        if profile.presentation_mode == "on_screen_hand":
            return "画面仅手部出镜，不露全脸；禁止复刻参考视频特定人物"
        return "出镜人物面部由模型生成，勿复刻参考视频特定人脸"
    if profile.voiceover_mode == VoiceoverMode.NONE:
        return "画面中禁止出现人物、人脸；无对白、无口型同步"
    if profile.voiceover_mode == VoiceoverMode.OFF_SCREEN:
        return "口播为画外音旁白，画面中禁止出现人物、人脸、口型同步"
    return ""
