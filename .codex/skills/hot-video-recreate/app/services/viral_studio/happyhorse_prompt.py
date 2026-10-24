"""Pass C：Happyhorse 四段式 prompt 编译（ai-video-prompt + R2V API）。"""
from __future__ import annotations

import re
from typing import List, Optional

from app.services.viral_studio.content_profile import VoiceoverMode
from app.services.viral_studio.happyhorse_refs import to_happyhorse_image_refs
from app.services.viral_studio.reference_roles import infer_reference_roles, resolve_reference_roles
from app.services.viral_studio.schemas import AdaptedScript, InferredProduct, ReferenceRole
from app.services.viral_studio.segment_merge import SegmentBundle, SubShotBundle
from app.services.viral_studio.voiceover_languages import (
    is_non_chinese_voiceover,
    voiceover_language_label,
)

_ROLE_DECL_LABELS = {
    "product": "产品参考",
    "character": "出镜人物参考",
    "scene": "场景参考",
    "other": "参考",
}

_ABSTRACT_MOTION_KEYWORDS = ("背对", "背身", "望向", "看向远方", "回眸")

_SHOT_SIZE_KEYWORDS = (
    ("特写", ("特写", "close", "CU")),
    ("大全景", ("大全景", "远景", "wide")),
    ("全景", ("全景", "FS")),
    ("中景", ("中景", "MS", "medium")),
    ("近景", ("近景", "近特写")),
)


def _fmt_time_range(start: float, end: float) -> str:
    s = max(0, int(start))
    e = max(s + 1, int(end))
    return f"{s}-{e}秒"


def _infer_shot_size(camera_cut: str) -> str:
    cam = (camera_cut or "").lower()
    for label, keys in _SHOT_SIZE_KEYWORDS:
        for k in keys:
            if k.lower() in cam:
                return label
    return "中景"


def _product_index(roles: List[ReferenceRole], face_ref_index: int) -> int:
    for r in roles:
        if r.role == "product":
            return r.index
    if face_ref_index == 1:
        return 2 if any(r.index == 2 for r in roles) else 1
    return 1


def _character_index(roles: List[ReferenceRole], face_ref_index: int) -> int:
    for r in roles:
        if r.role == "character":
            return r.index
    return face_ref_index if face_ref_index > 0 else 0


def build_reference_declaration(roles: List[ReferenceRole]) -> str:
    if not roles:
        return "[Image 1]为产品参考。"
    role_word = {"product": "产品", "character": "出镜人物", "scene": "场景"}
    parts: List[str] = []
    for r in sorted(roles, key=lambda x: x.index):
        if r.role == "other":
            continue
        suffix = _ROLE_DECL_LABELS.get(r.role, "参考")
        label = (r.label or "").strip()
        word = role_word.get(r.role, "")
        if label:
            if word and word not in label:
                parts.append(f"[Image {r.index}]为{label}{word}参考")
            else:
                parts.append(f"[Image {r.index}]为{label}参考")
        else:
            parts.append(f"[Image {r.index}]为{suffix}")
    if not parts:
        return "[Image 1]为产品参考。"
    return "，".join(parts) + "。"


def build_style_section(bundle: SegmentBundle) -> str:
    gc = bundle.global_consistency
    genre = (bundle.genre or "口播带货短视频").strip()
    tone = (gc.tone or "素人分享").strip()
    ratio = (bundle.aspect_ratio or "9:16").strip()
    parts = [
        genre,
        f"{tone}语气",
        f"{ratio}竖屏" if "9:16" in ratio or "竖" in ratio else f"{ratio}画幅",
        "写实直播质感",
        "暖色室内自然光",
        "浅景深",
        "手持轻微晃动",
    ]
    return "，".join(parts) + "。"


def _card_line(index: int, label: str, detail: str) -> str:
    lbl = (label or "").strip()
    det = (detail or "").strip()
    if lbl and det and lbl not in det:
        return f"[Image {index}]中的{lbl}，{det}"
    if det:
        return f"[Image {index}]中的{det}"
    if lbl:
        return f"[Image {index}]中的{lbl}"
    return f"[Image {index}]参考主体"


def build_character_product_cards(
    bundle: SegmentBundle,
    roles: List[ReferenceRole],
    *,
    face_ref_index: int,
    inferred_product: Optional[InferredProduct],
) -> str:
    gc = bundle.global_consistency
    lines: List[str] = []
    prod_idx = _product_index(roles, face_ref_index)
    char_idx = _character_index(roles, face_ref_index)

    if char_idx > 0:
        char_role = next((r for r in roles if r.index == char_idx), None)
        char_label = (char_role.label if char_role else "") or (gc.character or "出镜人物")
        char_detail = (gc.character or "").strip()
        if char_detail and char_detail == char_label:
            char_detail = "五官、发型、妆造与参考图一致，亲和分享情绪"
        elif not char_detail:
            char_detail = "五官、发型、妆造与参考图一致"
        lines.append(_card_line(char_idx, char_label, char_detail))

    prod_role = next((r for r in roles if r.index == prod_idx), None)
    prod_name = ""
    prod_traits = ""
    if inferred_product:
        prod_name = (inferred_product.name or "").strip()
        prod_traits = (inferred_product.visual_traits or "").strip()
    prod_label = (prod_role.label if prod_role else "") or prod_name or "产品"
    prod_detail = prod_traits or "全程产品外观与参考图一致，标签清晰可辨"
    lines.append(_card_line(prod_idx, prod_label, prod_detail))

    return "\n".join(lines)


def _motion_text(shot: SubShotBundle) -> str:
    motion = (shot.six.motion or "").strip()
    spatial = "；".join(shot.spatial or shot.six.spatial or [])
    camera = (shot.six.camera_cut or shot.camera_intent or "").strip()
    for kw in _ABSTRACT_MOTION_KEYWORDS:
        if kw in motion and spatial:
            return spatial
        if kw in motion and camera:
            return camera
    parts = [p for p in (motion, spatial) if p]
    return "，".join(parts) if parts else (shot.shot_intent or "自然展示")


def _audio_block(shot: SubShotBundle, character: str, *, off_screen: bool = False) -> str:
    vo = (
        shot.voiceover_verbatim
        or shot.six.audio.voiceover_performed
        or shot.six.audio.voiceover_semantic
        or ""
    ).strip()
    if not vo:
        return ""
    tone = (shot.six.audio.tone_label or shot.emotion or "").strip()
    delivery = (shot.six.audio.delivery_prompt or "").strip()
    if off_screen:
        speaker = "画外音"
    else:
        speaker = (character or "博主").strip()[:20]
    if delivery:
        return f"【音频】[{speaker}，{delivery}]「{vo}」"
    if tone:
        return f"【音频】[{speaker}，{tone}]「{vo}」"
    return f"【音频】[{speaker}]「{vo}」"


def build_shot_narrative(bundle: SegmentBundle) -> str:
    gc = bundle.global_consistency
    off_screen = bundle.voiceover_mode == VoiceoverMode.OFF_SCREEN.value
    character = (gc.character or "").strip()
    if not bundle.has_on_screen_person and not bundle.face_ref_index:
        character = ""
    elif not character and bundle.has_on_screen_person:
        character = "博主"
    lines: List[str] = []
    if not bundle.sub_shots:
        lines.append(
            f"第1个镜头[{_fmt_time_range(bundle.start_sec, bundle.end_sec)}] "
            f"[中景] 连贯呈现产品使用场景。"
        )
        if bundle.full_voiceover_verbatim:
            lines.append(
                _audio_block(
                    SubShotBundle(voiceover_verbatim=bundle.full_voiceover_verbatim),
                    character,
                    off_screen=off_screen,
                )
            )
        return "\n".join(l for l in lines if l)

    for i, shot in enumerate(bundle.sub_shots, start=1):
        tr = _fmt_time_range(shot.start_sec, shot.end_sec)
        size = _infer_shot_size(shot.six.camera_cut or shot.camera_intent)
        subject = (shot.six.subject or "").strip()
        motion = _motion_text(shot)
        env = (shot.six.environment or shot.visual_brief or "").strip()
        aesthetic = (shot.six.aesthetic or shot.emotion or "").strip()

        body_parts = [p for p in (subject, motion) if p]
        if env and env not in " ".join(body_parts):
            body_parts.append(env)
        if aesthetic and aesthetic not in " ".join(body_parts):
            body_parts.append(aesthetic)
        body = "，".join(body_parts) if body_parts else motion

        header = f"第{i}个镜头[{tr}] [{size}] {body}。"
        lines.append(header.rstrip("。。") + ("。" if not header.endswith("。") else ""))
        audio = _audio_block(shot, character, off_screen=off_screen)
        if audio:
            lines.append(audio)

    if bundle.continuity_from_prev:
        lines.append(f"承接上一段：{bundle.continuity_from_prev.strip()}。")

    return "\n".join(lines)


def build_happyhorse_footer(
    roles: List[ReferenceRole],
    *,
    face_ref_index: int,
    voiceover_language: str = "zh",
    voiceover_mode: str = VoiceoverMode.ON_SCREEN.value,
) -> str:
    prod_idx = _product_index(roles, face_ref_index)
    char_idx = _character_index(roles, face_ref_index)

    lines = [
        "画面仅呈现人物、产品与真实场景元素，无字幕、水印与屏显文字叠层。",
    ]
    if char_idx > 0:
        lines.append(f"人物面容、发型、妆造与[Image {char_idx}]一致；")
    lines.append(f"产品外观与[Image {prod_idx}]一致；")
    mode = voiceover_mode or VoiceoverMode.ON_SCREEN.value
    if mode == VoiceoverMode.ON_SCREEN.value:
        lip = "口型与台词自然同步，台词逐字准确。"
        if is_non_chinese_voiceover(voiceover_language):
            label = voiceover_language_label(voiceover_language)
            lip = f"Speaking in {label} with natural lip-sync; dialogue must match verbatim."
        lines.append(lip)
    elif mode == VoiceoverMode.OFF_SCREEN.value:
        lines.append("口播为画外音旁白，画面无人物出镜，无口型同步。")
    return "".join(lines)


def build_happyhorse_prompt(
    bundle: SegmentBundle,
    *,
    reference_image_urls: List[str],
    face_ref_index: int = 0,
    adapted_script: Optional[AdaptedScript] = None,
) -> str:
    """四段式 Happyhorse R2V prompt（写作层用参考图N，输出统一 [Image N]）。"""
    roles = resolve_reference_roles(
        adapted_script,
        reference_image_urls=reference_image_urls,
        face_ref_index=face_ref_index,
    )
    inferred = adapted_script.inferred_product if adapted_script else None

    sections = [
        build_reference_declaration(roles),
        build_style_section(bundle),
        build_character_product_cards(
            bundle,
            roles,
            face_ref_index=face_ref_index,
            inferred_product=inferred,
        ),
        build_shot_narrative(bundle),
        build_happyhorse_footer(
            roles,
            face_ref_index=face_ref_index,
            voiceover_language=bundle.voiceover_language or "zh",
            voiceover_mode=bundle.voiceover_mode,
        ),
    ]
    raw = "\n\n".join(s for s in sections if s.strip())
    return to_happyhorse_image_refs(raw)


SEEDANCE_PROMPT_TAGS = ("【主题】", "【视觉锚点】", "【段内分镜】", "【全段口播（逐字保留）】")


def happyhorse_structure_preserved(output: str) -> bool:
    """校验 Happyhorse 四段式结构，拒绝 Seedance 标签。"""
    text = (output or "").strip()
    if not text:
        return False
    if not re.search(r"\[Image\s+\d+\]", text):
        return False
    if not re.search(r"为.+参考", text):
        return False
    for tag in SEEDANCE_PROMPT_TAGS:
        if tag in text:
            return False
    return True
