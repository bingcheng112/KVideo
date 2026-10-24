"""原片呈现画像：展示形态、手部/出镜模式、generic 虚拟博主。"""
from __future__ import annotations

import re
from typing import List, Literal, Set

from app.services.viral_studio.gender_align import detect_dna_gender
from app.services.viral_studio.schemas import PresentationProfile, VideoDNA

PresentationMode = Literal[
    "on_screen_face",
    "on_screen_hand",
    "on_screen_body",
    "off_screen",
    "none",
]

_FACE_PATTERNS = re.compile(r"人脸|面容|五官|露脸|博主|主播|模特|讲解者|host|女主播|男博主|女博主", re.I)
_HAND_PATTERNS = re.compile(r"手部|手指|手\b|手持|拿|举起|举至", re.I)
_BODY_PATTERNS = re.compile(r"全身|半身|出镜|对镜|口播", re.I)
_NARRATOR_PATTERNS = re.compile(r"^narrator$|^画外音$|^旁白$|^voiceover$", re.I)

_HANDHELD_PATTERNS = re.compile(r"手持|举起|拿|握|旋转展示|举至|胸前", re.I)
_HANGING_PATTERNS = re.compile(
    r"悬挂|吊挂|挂于(?!衣)|挂拍|挂穿|挂展示|挂式|挂有|整体挂|悬空",
    re.I,
)
_HANGING_ON_RACK = re.compile(r"挂于衣架|悬挂在衣架|吊挂在衣架|挂在衣架", re.I)
_RACK_ACTION_RE = re.compile(
    r"手持衣架|手提衣架|提衣架|拎着衣架|晃动衣架|摇动衣架",
    re.I,
)
_RACK_SPATIAL_RE = re.compile(r"衣架居中|衣架位于|产品挂于衣架|内衣挂于衣架", re.I)
_MIRROR_PATTERNS = re.compile(r"对镜|口播|面对镜头", re.I)


def _str(v) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _collect_timeline_texts(video_dna: VideoDNA) -> List[str]:
    parts: List[str] = []
    for entry in video_dna.timeline or []:
        if entry.performance:
            parts.append(_str(entry.performance))
        if entry.product_presence:
            parts.append(_str(entry.product_presence))
        if entry.shot_intent:
            parts.append(_str(entry.shot_intent))
        vis = entry.visual or {}
        if vis.get("environment"):
            parts.append(_str(vis["environment"]))
        for subj in vis.get("subjects") or []:
            if not isinstance(subj, dict):
                continue
            for key in ("role", "id", "desc", "action"):
                if subj.get(key):
                    parts.append(_str(subj[key]))
        audio = entry.audio
        if audio and audio.voiceover:
            if audio.voiceover.speaker:
                parts.append(_str(audio.voiceover.speaker))
            if audio.voiceover.text:
                parts.append(_str(audio.voiceover.text))
        spatial = entry.spatial or {}
        if isinstance(spatial, dict):
            for rel in spatial.get("relations") or []:
                if rel:
                    parts.append(_str(rel))
        elif isinstance(spatial, list):
            for rel in spatial:
                if rel:
                    parts.append(_str(rel))
    return [p for p in parts if p]


def _is_narrator_only(video_dna: VideoDNA) -> bool:
    speakers: Set[str] = set()
    for entry in video_dna.timeline or []:
        audio = entry.audio
        if audio and audio.voiceover and audio.voiceover.speaker:
            speakers.add(_str(audio.voiceover.speaker).lower())
    if not speakers:
        return False
    return all(_NARRATOR_PATTERNS.search(s) for s in speakers)


def _infer_display_style(blob: str) -> str:
    if _HANGING_PATTERNS.search(blob) and not _HANDHELD_PATTERNS.search(blob):
        return "悬挂展示"
    if _HANDHELD_PATTERNS.search(blob):
        return "手持展示"
    if _MIRROR_PATTERNS.search(blob):
        return "对镜口播"
    if _HAND_PATTERNS.search(blob):
        return "手部展示"
    return "产品展示"


def _infer_mode(video_dna: VideoDNA, blob: str) -> PresentationMode:
    if not video_dna.timeline:
        return "none"
    if _is_narrator_only(video_dna):
        return "off_screen"
    if _FACE_PATTERNS.search(blob):
        return "on_screen_face"
    if _HAND_PATTERNS.search(blob):
        return "on_screen_hand"
    if _BODY_PATTERNS.search(blob):
        return "on_screen_body"
    return "off_screen"


def _collect_actions(video_dna: VideoDNA) -> List[str]:
    actions: List[str] = []
    for entry in video_dna.timeline or []:
        if entry.performance:
            actions.append(_str(entry.performance))
        vis = entry.visual or {}
        for subj in vis.get("subjects") or []:
            if isinstance(subj, dict) and subj.get("action"):
                actions.append(_str(subj["action"]))
    return list(dict.fromkeys(a for a in actions if a))[:8]


def _collect_scene_type(video_dna: VideoDNA) -> str:
    envs: List[str] = []
    for entry in video_dna.timeline or []:
        vis = entry.visual or {}
        env = _str(vis.get("environment"))
        if env:
            envs.append(env)
    if not envs:
        return ""
    return max(envs, key=len)


def _build_generic_character(mode: PresentationMode, video_dna: VideoDNA) -> str:
    gender = detect_dna_gender(video_dna)
    if mode == "on_screen_hand":
        if gender == "female":
            return "女性手部模特，自然肤色，非特定名人"
        if gender == "male":
            return "男性手部模特，自然肤色，非特定名人"
        return "手部模特，自然肤色，非特定名人"
    if gender == "female":
        return "年轻女性博主，自然五官，非特定名人"
    if gender == "male":
        return "年轻男性博主，自然五官，非特定名人"
    return "年轻博主，自然五官，非特定名人"


def extract_presentation_profile(video_dna: VideoDNA) -> PresentationProfile:
    """从 DNA 提取呈现画像（规则，无 LLM）。"""
    texts = _collect_timeline_texts(video_dna)
    blob = " ".join(texts)
    mode = _infer_mode(video_dna, blob)
    display_style = _infer_display_style(blob)
    return PresentationProfile(
        mode=mode,
        display_style=display_style,
        typical_actions=_collect_actions(video_dna),
        scene_type=_collect_scene_type(video_dna),
        generic_character=_build_generic_character(mode, video_dna),
    )


def requires_generic_person(
    presentation: PresentationProfile,
    *,
    has_face_ref: bool,
) -> bool:
    """原片需要呈现人物/手部，但用户未指定人脸参考。"""
    if has_face_ref:
        return False
    return presentation.mode in (
        "on_screen_face",
        "on_screen_hand",
        "on_screen_body",
    )


def presentation_has_person(presentation: PresentationProfile) -> bool:
    return presentation.mode in (
        "on_screen_face",
        "on_screen_hand",
        "on_screen_body",
    )


def is_handheld_style(display_style: str) -> bool:
    return display_style in ("手持展示", "手部展示", "对镜口播", "产品展示")


def is_hanging_style(text: str) -> bool:
    t = text or ""
    if _HANGING_PATTERNS.search(t):
        return True
    if _HANGING_ON_RACK.search(t):
        return True
    if _RACK_ACTION_RE.search(t):
        return True
    if _RACK_SPATIAL_RE.search(t):
        return True
    return False


def should_inherit_handheld(presentation: PresentationProfile) -> bool:
    """原片有人物呈现且非纯悬挂展示时，应继承手持/对镜形态。"""
    if is_handheld_style(presentation.display_style):
        return True
    if presentation.mode in ("on_screen_face", "on_screen_hand", "on_screen_body"):
        return presentation.display_style != "悬挂展示"
    return False


def replace_hanging_phrases(
    text: str,
    *,
    replacement: str = "手持展示",
    product_ref: str = "参考图1",
) -> str:
    """将悬挂/挂拍/产品图衣架陈列类表述替换为手持或穿着。"""
    if not text:
        return text
    t = text
    handheld_product = f"手持{product_ref}产品"
    carry_product = f"手提{product_ref}产品"
    t = re.sub(r"挂于衣架上?", "被博主手持展示", t)
    t = re.sub(r"悬挂在衣架上?", "被博主手持展示", t)
    t = re.sub(r"吊挂在衣架上?", "被博主手持展示", t)
    t = re.sub(r"挂在衣架上?", "被博主手持展示", t)
    t = re.sub(r"产品挂于衣架(?:上)?", f"{product_ref}产品被博主手持展示", t)
    t = re.sub(r"内衣挂于衣架(?:上)?", f"{product_ref}产品被博主手持展示", t)
    t = re.sub(r"手提衣架", carry_product, t)
    t = re.sub(r"提衣架|拎着衣架", handheld_product, t)
    t = re.sub(r"手持衣架", handheld_product, t)
    t = re.sub(r"晃动衣架|摇动衣架", "轻微晃动产品", t)
    t = re.sub(r"衣架居中", "产品位于画面中央", t)
    t = re.sub(r"衣架位于(?:画面)?中央", "产品位于画面中央", t)
    t = re.sub(r"衣架位于[^；;，,\s]+", "产品位于画面中央", t)
    t = re.sub(r"手持展示上", "被博主手持展示", t)
    t = re.sub(r"展示手持展示后", "展示手持", t)
    t = re.sub(r"挂拍效果?", "手持展示效果", t, flags=re.I)
    t = re.sub(r"挂穿", "穿着", t, flags=re.I)
    t = re.sub(r"整体挂(?:拍|展示)?", "整体手持展示", t, flags=re.I)
    t = re.sub(r"悬空于", "被手持悬于", t)
    t = re.sub(r"悬空(?!于)", "被手持悬于", t)
    return _HANGING_PATTERNS.sub(replacement, t)
