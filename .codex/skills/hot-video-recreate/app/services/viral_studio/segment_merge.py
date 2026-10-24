"""Seedance 段内多镜合并与确定性 prompt 模板（六要素版）。"""
from __future__ import annotations

import re
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.services.viral_studio.content_profile import (
    ContentProfile,
    VoiceoverMode,
    constraint_suffix_for_profile,
    is_placeholder_text,
    theme_line_for_profile,
)
from app.services.viral_studio.llm_normalize import resolve_transition_out
from app.services.viral_studio.schemas import (
    AdaptedScene,
    AdaptedScript,
    GlobalConsistency,
    ReferenceRole,
    ShotPromptSix,
    VideoDNA,
)
from app.services.viral_studio.seedance_refs import (
    build_seedance_reference_declaration,
    product_constraint_ref,
)
from app.services.viral_studio.six_elements import (
    build_scene_six,
    dna_entry_to_six,
    match_omni_entry_dict,
)
from app.services.face_compliance.prompt_templates import face_ref_anchor_text
from app.services.viral_studio.voice_delivery import refine_voice_delivery
from app.services.viral_studio.voiceover_languages import (
    is_non_chinese_voiceover,
    voiceover_language_label,
)


class SubShotBundle(BaseModel):
    start_sec: float = 0
    end_sec: float = 0
    beat_role: str = ""
    emotion: str = ""
    shot_intent: str = ""
    six: ShotPromptSix = Field(default_factory=ShotPromptSix)
    transition_out: str = ""
    # 兼容旧测试/VC bundle JSON
    voiceover_verbatim: str = ""
    visual_brief: str = ""
    camera_intent: str = ""
    omni_visual: str = ""
    spatial: List[str] = Field(default_factory=list)


class SegmentBundle(BaseModel):
    segment_index: int = 0
    start_sec: float = 0
    end_sec: float = 0
    duration: float = 0
    task_type: Literal["i2v", "r2v"] = "i2v"
    genre: str = ""
    aspect_ratio: str = "9:16"
    global_consistency: GlobalConsistency = Field(default_factory=GlobalConsistency)
    sub_shots: List[SubShotBundle] = Field(default_factory=list)
    full_voiceover_verbatim: str = ""
    audio_hints: str = ""
    continuity_from_prev: Optional[str] = None
    face_ref_index: int = 0
    face_ref_mode: str = "pencil"
    voiceover_language: str = "zh"
    voiceover_mode: str = VoiceoverMode.ON_SCREEN.value
    has_on_screen_person: bool = True
    requires_generic_person: bool = False
    presentation_mode: str = "none"
    reference_roles: List[ReferenceRole] = Field(default_factory=list)


def _overlaps(start: float, end: float, seg_start: float, seg_end: float) -> bool:
    return seg_end > start and seg_start < end


def _scenes_in_range(script: AdaptedScript, start: float, end: float) -> List[AdaptedScene]:
    out: List[AdaptedScene] = []
    for scene in script.adapted_script:
        s = float(scene.start_sec or 0)
        e = float(scene.end_sec or 0)
        if e <= s:
            continue
        if _overlaps(start, end, s, e):
            out.append(scene)
    out.sort(key=lambda x: float(x.start_sec or 0))
    return out


def _timeline_in_range(dna: VideoDNA, start: float, end: float) -> List[dict]:
    out: List[dict] = []
    for entry in dna.timeline:
        s = float(entry.start)
        e = float(entry.end)
        if e <= start or s >= end:
            continue
        out.append(entry.model_dump())
    return out


def _audio_hints_from_timeline(entries: List[dict]) -> str:
    parts: List[str] = []
    for e in entries:
        audio = e.get("audio") or {}
        if audio.get("bgm"):
            parts.append(str(audio["bgm"]))
        if audio.get("ambient"):
            parts.append(str(audio["ambient"]))
        sfx = str(audio.get("sfx") or "").strip()
        if sfx:
            at_sec = audio.get("sfx_at_sec")
            try:
                sec = float(at_sec) if at_sec is not None else 0.0
            except (TypeError, ValueError):
                sec = 0.0
            if sec > 0:
                parts.append(f"{sec:g}秒：{sfx}")
            else:
                parts.append(sfx)
    return "；".join(dict.fromkeys(parts))


def _merge_voiceover_parts(parts: List[str]) -> str:
    cleaned: List[str] = []
    seen: set[str] = set()
    for p in parts:
        t = (p or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        cleaned.append(t)
    if not cleaned:
        return ""
    return " ".join(cleaned)


def _voiceover_for_shot(six: ShotPromptSix, fallback: str = "") -> str:
    performed = (six.audio.voiceover_performed or "").strip()
    if performed:
        return performed
    semantic = (six.audio.voiceover_semantic or fallback or "").strip()
    return semantic


def _scene_to_sub_shot(
    scene: AdaptedScene,
    omni: Optional[dict],
    global_tone: str,
    default_start: float,
    default_end: float,
    profile: Optional[ContentProfile] = None,
) -> SubShotBundle:
    s = float(scene.start_sec or default_start)
    e = float(scene.end_sec or default_end)
    merged_six = build_scene_six(scene, omni, global_tone=global_tone)

    temp_scene = AdaptedScene(
        scene_id=scene.scene_id,
        beat_role=scene.beat_role,
        emotion=scene.emotion,
        shot_intent=scene.shot_intent,
        six=merged_six,
        new_voiceover=merged_six.audio.voiceover_semantic or scene.new_voiceover,
    )
    temp_scene = refine_voice_delivery(
        temp_scene,
        environment=merged_six.environment,
        global_tone=global_tone,
        profile=profile,
    )
    six = temp_scene.six
    vo = _voiceover_for_shot(six, scene.new_voiceover)

    tr_out = ""
    if omni:
        tr = resolve_transition_out(omni)
        tr_out = str(tr.get("type") or "")

    return SubShotBundle(
        start_sec=round(s, 1),
        end_sec=round(e, 1),
        beat_role=(scene.beat_role or (omni or {}).get("beat_role") or "").strip(),
        emotion=(scene.emotion or six.audio.emotion or "").strip(),
        shot_intent=(scene.shot_intent or "").strip(),
        six=six,
        transition_out=tr_out,
        voiceover_verbatim=vo,
        visual_brief=six.environment or (scene.visual_brief or ""),
        camera_intent=six.camera_cut or (scene.camera or ""),
        spatial=list(six.spatial or []),
    )


def build_segment_bundle(
    *,
    segment_index: int,
    start_sec: float,
    end_sec: float,
    duration: float,
    task_type: Literal["i2v", "r2v"],
    video_dna: VideoDNA,
    adapted_script: AdaptedScript,
    face_ref_index: int = 0,
    face_ref_mode: str = "pencil",
    profile: Optional[ContentProfile] = None,
    reference_roles: Optional[List[ReferenceRole]] = None,
) -> SegmentBundle:
    gc = adapted_script.global_consistency
    global_tone = (gc.tone or "").strip()
    scenes = _scenes_in_range(adapted_script, start_sec, end_sec)
    tl_slice = _timeline_in_range(video_dna, start_sec, end_sec)

    sub_shots: List[SubShotBundle] = []
    vo_parts: List[str] = []

    if scenes:
        for scene in scenes:
            s = float(scene.start_sec or start_sec)
            e = float(scene.end_sec or end_sec)
            omni = match_omni_entry_dict(tl_slice, s, e)
            shot = _scene_to_sub_shot(scene, omni, global_tone, start_sec, end_sec, profile)
            sub_shots.append(shot)
            if shot.voiceover_verbatim:
                vo_parts.append(shot.voiceover_verbatim)
    elif tl_slice:
        for entry in tl_slice:
            s = float(entry.get("start") or start_sec)
            e = float(entry.get("end") or end_sec)
            six = dna_entry_to_six(entry)
            temp = AdaptedScene(
                start_sec=s,
                end_sec=e,
                beat_role=str(entry.get("beat_role") or ""),
                emotion=str(entry.get("emotion") or ""),
                shot_intent=str(entry.get("shot_intent") or ""),
                six=six,
            )
            temp = refine_voice_delivery(
                temp,
                environment=six.environment,
                global_tone=global_tone,
                profile=profile,
            )
            six = temp.six
            vo = _voiceover_for_shot(six)
            if vo:
                vo_parts.append(vo)
            tr = resolve_transition_out(entry)
            sub_shots.append(
                SubShotBundle(
                    start_sec=round(s, 1),
                    end_sec=round(e, 1),
                    beat_role=str(entry.get("beat_role") or ""),
                    emotion=str(entry.get("emotion") or ""),
                    shot_intent=str(entry.get("shot_intent") or ""),
                    six=six,
                    transition_out=str(tr.get("type") or "") if isinstance(tr, dict) else "",
                    voiceover_verbatim=vo,
                    visual_brief=six.environment,
                    camera_intent=six.camera_cut,
                    spatial=list(six.spatial or []),
                )
            )

    continuity = None
    if scenes and scenes[0].continuity_from_prev:
        continuity = scenes[0].continuity_from_prev

    meta = video_dna.meta
    mode = profile.voiceover_mode if profile else VoiceoverMode.ON_SCREEN
    has_person = profile.has_on_screen_person if profile else True
    needs_generic = profile.requires_generic_person if profile else False
    pres_mode = profile.presentation_mode if profile else "none"
    return SegmentBundle(
        segment_index=segment_index,
        start_sec=start_sec,
        end_sec=end_sec,
        duration=duration,
        task_type=task_type,
        genre=(meta.genre or "").strip(),
        aspect_ratio=(meta.aspect_ratio or "9:16").strip(),
        global_consistency=gc,
        sub_shots=sub_shots,
        full_voiceover_verbatim=_merge_voiceover_parts(vo_parts),
        audio_hints=_audio_hints_from_timeline(tl_slice),
        continuity_from_prev=continuity,
        face_ref_index=max(0, int(face_ref_index or 0)),
        face_ref_mode=(face_ref_mode or "pencil").strip().lower(),
        voiceover_mode=mode.value,
        has_on_screen_person=has_person,
        requires_generic_person=needs_generic,
        presentation_mode=pres_mode,
        reference_roles=list(reference_roles or []),
    )


def _bundle_profile(bundle: SegmentBundle) -> ContentProfile:
    try:
        mode = VoiceoverMode(bundle.voiceover_mode or VoiceoverMode.ON_SCREEN.value)
    except ValueError:
        mode = VoiceoverMode.ON_SCREEN
    return ContentProfile(
        has_voiceover=mode != VoiceoverMode.NONE,
        has_on_screen_person=bool(bundle.has_on_screen_person),
        voiceover_mode=mode,
        has_face_ref=int(bundle.face_ref_index or 0) > 0,
        requires_generic_person=bool(bundle.requires_generic_person),
        presentation_mode=(bundle.presentation_mode or "none").strip() or "none",
    )


def _fmt_sub_shot_six(shot: SubShotBundle, profile: ContentProfile) -> str:
    six = shot.six
    role = shot.beat_role or "分镜"
    emo = shot.emotion or six.audio.emotion
    emo_tag = f"|情绪:{emo}" if emo else ""
    header = f"【{shot.start_sec}-{shot.end_sec}s|{role}{emo_tag}】"

    lines: List[str] = [header]
    if six.subject:
        lines.append(f"主体：{six.subject}")
    if six.motion:
        lines.append(f"运动：{six.motion}")

    env_parts: List[str] = []
    if six.environment:
        env_parts.append(six.environment)
    spatial = six.spatial or shot.spatial or []
    if spatial:
        env_parts.append(f"空间：{'；'.join(spatial)}")
    if env_parts:
        lines.append(f"环境：{'；'.join(env_parts)}")

    camera = six.camera_cut or shot.camera_intent
    if camera:
        cut = f"；段末{shot.transition_out}" if shot.transition_out and shot.transition_out not in camera else ""
        lines.append(f"运镜/切镜：{camera}{cut}")

    aesthetic = six.aesthetic or emo
    if aesthetic:
        lines.append(f"美学：{aesthetic}")

    audio_lines: List[str] = []
    vo = shot.voiceover_verbatim or six.audio.voiceover_performed or six.audio.voiceover_semantic
    if profile.voiceover_mode != VoiceoverMode.NONE and six.audio.delivery_prompt:
        audio_lines.append(f"【发声】{six.audio.delivery_prompt}")
    if vo:
        audio_lines.append(f"【台词】「{vo}」")
        if six.audio.tone_label:
            audio_lines.append(f"语气：{six.audio.tone_label}")
    elif profile.voiceover_mode != VoiceoverMode.NONE:
        audio_lines.append("本镜无新口播，延续画面演示")
    bgm_parts = [p for p in [six.audio.bgm, six.audio.ambient] if p]
    if six.audio.sfx:
        audio_lines.append(f"音效：{six.audio.sfx}")
    if bgm_parts:
        audio_lines.append(f"BGM/环境音：{'；'.join(bgm_parts)}")
    if audio_lines:
        lines.append("音频：" + " ".join(audio_lines))

    if shot.shot_intent:
        lines.append(f"意图：{shot.shot_intent}")

    return " ".join(lines)


def build_deterministic_prompt(bundle: SegmentBundle) -> str:
    """VC 关闭：六要素结构化多镜模板（performed 口播逐字保留）。"""
    gc = bundle.global_consistency
    profile = _bundle_profile(bundle)
    if profile.has_on_screen_person:
        char = (gc.character or "").strip()
        if not char or is_placeholder_text(char):
            fallback_char = (
                "女性手部模特，自然肤色，非特定名人"
                if profile.presentation_mode == "on_screen_hand"
                else "年轻博主，自然五官"
            )
            gc = gc.model_copy(update={"character": fallback_char})
    product_ref = gc.product_ref or "参考图1"
    roles = list(bundle.reference_roles or [])
    constraint_ref = product_constraint_ref(roles) if roles else product_ref
    lines: List[str] = []

    genre = bundle.genre or "口播带货短视频"
    tone = (gc.tone or "").strip()
    if is_placeholder_text(tone):
        tone = ""
    lines.append(f"【主题】{theme_line_for_profile(profile, genre, tone)}")
    anchor = f"【视觉锚点】{product_ref}产品全程清晰可辨"
    decl = build_seedance_reference_declaration(roles)
    if decl:
        anchor += f"；{decl.rstrip('。')}"
    if (
        profile.has_on_screen_person
        and gc.character
        and not is_placeholder_text(gc.character)
    ):
        anchor += f"，人物：{gc.character}"
    if bundle.face_ref_index and bundle.face_ref_index > 0:
        anchor += f"，{face_ref_anchor_text(bundle.face_ref_index, bundle.face_ref_mode)}"
    elif (
        profile.requires_generic_person
        and not bundle.face_ref_index
        and profile.presentation_mode != "on_screen_hand"
    ):
        anchor += "，人物面部由 AI 生成，勿复刻原视频特定人脸"
    lines.append(anchor + "。")

    if bundle.sub_shots:
        lines.append(
            f"【段内分镜 {bundle.start_sec}-{bundle.end_sec}s】"
            + " ".join(_fmt_sub_shot_six(s, profile) for s in bundle.sub_shots)
        )
    else:
        lines.append(f"【画面】{bundle.start_sec}-{bundle.end_sec}s 连贯呈现产品使用场景。")

    if bundle.continuity_from_prev:
        lines.append(f"【承接】{bundle.continuity_from_prev}。")

    if bundle.full_voiceover_verbatim:
        lines.append(f"【全段口播（逐字保留）】「{bundle.full_voiceover_verbatim}」")

    if bundle.audio_hints:
        lines.append(f"【背景音】{bundle.audio_hints}。")

    if (
        is_non_chinese_voiceover(bundle.voiceover_language)
        and bundle.full_voiceover_verbatim
        and profile.voiceover_mode == VoiceoverMode.ON_SCREEN
    ):
        label = voiceover_language_label(bundle.voiceover_language)
        lines.append(
            f"【语言】Speaking in {label} with natural lip-sync; "
            "dialogue must match the verbatim voiceover block."
        )

    extra = constraint_suffix_for_profile(profile)
    if bundle.task_type == "r2v":
        constraint = (
            f"【约束】以参考视频为运镜与节奏基准，严格跟随其镜头切分；"
            f"将画面商品替换为{constraint_ref}；禁止字幕、水印、屏显文字。"
        )
    else:
        constraint = (
            f"【约束】按上述分镜时间顺序连贯呈现，每镜切换处执行对应切镜方式；"
            f"产品在画面中完整展示；禁止字幕、水印、屏显文字。"
        )
    if extra:
        constraint = constraint[:-1] + f"；{extra}。"
    lines.append(constraint)

    return "".join(lines)


def normalize_for_match(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[「」\"'『』【】]", "", t)
    return t


def voiceover_preserved_in_output(output: str, verbatim: str) -> bool:
    """校验口播是否在输出中完整保留。"""
    if not verbatim or not verbatim.strip():
        return True
    norm_v = normalize_for_match(verbatim)
    norm_o = normalize_for_match(output)
    if not norm_v:
        return True
    if norm_v in norm_o:
        return True
    chunks = [
        c.strip()
        for c in re.split(r"[。！？；\n.!?;]", verbatim)
        if len(c.strip()) >= 4
    ]
    if not chunks:
        return norm_v in norm_o
    hit = sum(1 for c in chunks if normalize_for_match(c) in norm_o)
    return hit >= max(1, int(len(chunks) * 0.8))


def six_elements_preserved(output: str, bundle: SegmentBundle) -> bool:
    """校验六要素标签与发声块是否保留。"""
    if not bundle.sub_shots:
        return True
    profile = _bundle_profile(bundle)
    required_tags = ["主体：", "运动：", "环境：", "运镜", "美学："]
    if profile.voiceover_mode != VoiceoverMode.NONE:
        if profile.voiceover_mode == VoiceoverMode.ON_SCREEN:
            required_tags.extend(["【发声】", "【台词】"])
        elif bundle.full_voiceover_verbatim:
            required_tags.append("【台词】")
    for tag in required_tags:
        if tag not in output:
            return False
    for shot in bundle.sub_shots:
        if shot.six.audio.delivery_prompt and shot.six.audio.delivery_prompt not in output:
            # 允许 VC 改写措辞，但 performed 必须在
            if shot.voiceover_verbatim and shot.voiceover_verbatim not in output:
                norm_v = normalize_for_match(shot.voiceover_verbatim)
                if norm_v not in normalize_for_match(output):
                    return False
    return True
