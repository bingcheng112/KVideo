"""口播/画面人物性别与人称对齐（preserve 模式下手术式替换）。"""
from __future__ import annotations

from typing import Literal

from app.services.viral_studio.schemas import AdaptedScene, AdaptedScript, VideoDNA

GenderTarget = Literal["female", "male", "unknown"]

# 长词优先，避免「兄弟」先于「兄弟们」被替换
_TO_FEMALE: tuple[tuple[str, str], ...] = (
    ("兄弟们", "姐妹们"),
    ("兄弟伙", "姐妹淘"),
    ("小哥哥", "小姐姐"),
    ("大兄弟", "大姐妹"),
    ("老铁们", "姐妹们"),
    ("哥们", "姐妹"),
    ("兄弟", "姐妹"),
    ("老哥", "姐妹"),
    ("男生", "女生"),
    ("男人", "女生"),
    ("男孩", "女孩"),
    ("小伙", "女孩"),
    ("帅哥", "美女"),
    ("男博主", "女博主"),
    ("男主播", "女主播"),
    ("他", "她"),
)

_TO_MALE: tuple[tuple[str, str], ...] = tuple(
    sorted(((b, a) for a, b in _TO_FEMALE), key=lambda p: len(p[0]), reverse=True)
)

_FEMALE_HINTS = (
    "女",
    "姐妹",
    "小姐姐",
    "口红",
    "唇妆",
    "腮红",
    "睫毛",
    "蝴蝶结",
    "长发",
    "裙",
    "她",
)
_MALE_HINTS = (
    "男",
    "兄弟",
    "哥们",
    "老哥",
    "胡茬",
    "胡须",
    "他",
)


def _normalize_gender(value: str) -> GenderTarget:
    v = (value or "").strip().lower()
    if v in ("female", "f", "女", "woman"):
        return "female"
    if v in ("male", "m", "男", "man"):
        return "male"
    if v in ("neutral", "unknown", ""):
        return "unknown"
    return "unknown"


def infer_target_gender(
    character_summary: str = "",
    presented_gender: str = "",
) -> GenderTarget:
    """优先 presented_gender；否则从 character_summary 关键词推断。"""
    pg = _normalize_gender(presented_gender)
    if pg != "unknown":
        return pg

    summary = (character_summary or "").strip()
    if not summary:
        return "unknown"

    f_score = sum(1 for h in _FEMALE_HINTS if h in summary)
    m_score = sum(1 for h in _MALE_HINTS if h in summary)
    if f_score > m_score and f_score > 0:
        return "female"
    if m_score > f_score and m_score > 0:
        return "male"
    return "unknown"


def detect_source_gender(text: str) -> GenderTarget:
    """从 DNA 口播或人物描述检测原片性别倾向。"""
    t = (text or "").strip()
    if not t:
        return "unknown"

    m_score = 0
    f_score = 0
    # _TO_FEMALE 的 src 为偏男性/中性称呼，出现在原文表示原片偏男
    for src, _ in _TO_FEMALE:
        if src in t:
            m_score += len(src)
    # _TO_MALE 的 src 为偏女性称呼，出现在原文表示原片偏女
    for src, _ in _TO_MALE:
        if src in t:
            f_score += len(src)

    if f_score > m_score and f_score > 0:
        return "female"
    if m_score > f_score and m_score > 0:
        return "male"
    return "unknown"


def detect_dna_gender(video_dna: Optional[VideoDNA]) -> GenderTarget:
    """聚合 DNA timeline 口播与人物描述。"""
    if not video_dna:
        return "unknown"
    parts: list[str] = []
    for entry in video_dna.timeline or []:
        if entry.audio and entry.audio.voiceover:
            parts.append(entry.audio.voiceover.text or "")
        vis = entry.visual or {}
        for subj in vis.get("subjects") or []:
            if isinstance(subj, dict):
                parts.append(str(subj.get("desc") or ""))
                parts.append(str(subj.get("action") or ""))
        parts.append(str(entry.performance or ""))
    return detect_source_gender(" ".join(parts))


def _apply_pairs(text: str, pairs: tuple[tuple[str, str], ...]) -> str:
    if not text:
        return text
    out = text
    for src, dst in pairs:
        out = out.replace(src, dst)
    return out


def align_gender_in_text(text: str, target: GenderTarget) -> str:
    """将文本中的人称/性别词对齐到 target；unknown 时 no-op。"""
    t = (text or "").strip()
    if not t or target == "unknown":
        return text or ""

    if target == "female":
        return _apply_pairs(t, _TO_FEMALE)
    if target == "male":
        return _apply_pairs(t, _TO_MALE)
    return text


def should_align_gender(
    target: GenderTarget,
    source: GenderTarget,
) -> bool:
    if target == "unknown":
        return False
    if source == "unknown":
        return True
    return target != source


def align_scene_gender(scene: AdaptedScene, target: GenderTarget) -> AdaptedScene:
    if target == "unknown":
        return scene

    if scene.new_voiceover:
        scene.new_voiceover = align_gender_in_text(scene.new_voiceover, target)
    if scene.shot_intent:
        scene.shot_intent = align_gender_in_text(scene.shot_intent, target)
    if scene.six:
        if scene.six.subject:
            scene.six.subject = align_gender_in_text(scene.six.subject, target)
        if scene.six.motion:
            scene.six.motion = align_gender_in_text(scene.six.motion, target)
        if scene.six.audio.voiceover_semantic:
            scene.six.audio.voiceover_semantic = align_gender_in_text(
                scene.six.audio.voiceover_semantic, target
            )
        if scene.six.audio.voiceover_performed:
            scene.six.audio.voiceover_performed = align_gender_in_text(
                scene.six.audio.voiceover_performed, target
            )
    return scene


def align_script_gender(script: AdaptedScript, target: GenderTarget) -> AdaptedScript:
    if target == "unknown":
        return script
    for scene in script.adapted_script:
        align_scene_gender(scene, target)
    if script.global_consistency.character:
        script.global_consistency.character = align_gender_in_text(
            script.global_consistency.character, target
        )
    return script
