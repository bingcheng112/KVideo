"""Seedance 六要素：DNA 映射、合并与旧版兼容。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from app.services.viral_studio.llm_normalize import resolve_transition_out
from app.services.viral_studio.schemas import (
    AdaptedScene,
    ShotAudio,
    ShotPromptSix,
    TimelineEntry,
    VideoDNA,
)


def _str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _spatial_from_entry(entry: Union[TimelineEntry, dict]) -> List[str]:
    if isinstance(entry, TimelineEntry):
        spatial = entry.spatial or {}
    else:
        spatial = entry.get("spatial") or {}
    if isinstance(spatial, list):
        return [_str(r) for r in spatial if _str(r)]
    if isinstance(spatial, dict):
        return [_str(r) for r in (spatial.get("relations") or []) if r]
    if isinstance(spatial, str) and spatial.strip():
        return [_str(spatial)]
    return []


def _subjects_parts(entry: Union[TimelineEntry, dict]) -> tuple[str, str]:
    if isinstance(entry, TimelineEntry):
        vis = entry.visual or {}
    else:
        vis = entry.get("visual") or {}
    descs: List[str] = []
    actions: List[str] = []
    for subj in vis.get("subjects") or []:
        if not isinstance(subj, dict):
            continue
        if subj.get("desc"):
            descs.append(_str(subj["desc"]))
        if subj.get("action"):
            actions.append(_str(subj["action"]))
    return "，".join(dict.fromkeys(descs)), "，".join(dict.fromkeys(actions))


def _format_sfx(audio: dict) -> str:
    sfx = _str(audio.get("sfx"))
    if not sfx:
        return ""
    at_sec = audio.get("sfx_at_sec")
    try:
        sec = float(at_sec) if at_sec is not None else 0.0
    except (TypeError, ValueError):
        sec = 0.0
    if sec > 0:
        return f"{sec:g}秒处{sfx}"
    return sfx


def _build_camera_cut(data: dict, vis: dict) -> str:
    edit = data.get("edit") or {}
    if not isinstance(edit, dict):
        edit = {}

    camera = _str(vis.get("camera"))
    camera_motion = _str(vis.get("camera_motion"))
    cut_type = _str(edit.get("cut_type"))

    parts: List[str] = []
    if camera:
        parts.append(camera)
    if camera_motion and camera_motion not in camera:
        parts.append(camera_motion)
    if cut_type:
        parts.append(cut_type)

    tr = resolve_transition_out(data)
    tr_type = _str(tr.get("type") if isinstance(tr, dict) else "")
    tr_dur = tr.get("duration_sec") if isinstance(tr, dict) else None
    end_sec = float(data.get("end") or 0)

    if tr_type:
        if end_sec > 0:
            transition_desc = f"{end_sec:g}秒处{tr_type}"
        else:
            transition_desc = f"段末{tr_type}"
        if tr_dur:
            try:
                dur = float(tr_dur)
                if dur > 0:
                    transition_desc = f"{transition_desc}（{dur:g}s）"
            except (TypeError, ValueError):
                pass
        parts.append(transition_desc)

    return "；".join(dict.fromkeys(p for p in parts if p))


def dna_entry_to_six(entry: Union[TimelineEntry, dict, None]) -> ShotPromptSix:
    """DNA timeline 一条 → ShotPromptSix。"""
    if entry is None:
        return ShotPromptSix()

    if isinstance(entry, TimelineEntry):
        data = entry.model_dump()
    else:
        data = entry

    vis = data.get("visual") or {}
    audio = data.get("audio") or {}
    vo = audio.get("voiceover") or {}
    if not isinstance(vo, dict):
        vo = {}

    subj_desc, subj_action = _subjects_parts(data)
    subject_parts = [p for p in [subj_desc, _str(data.get("product_presence"))] if p]
    motion_parts = [p for p in [subj_action, _str(data.get("performance"))] if p]

    style_tags = vis.get("style_tags") or []
    if isinstance(style_tags, str):
        style_tags = [style_tags.strip()] if style_tags.strip() else []
    in_shot = vis.get("in_shot_effects") or []
    if isinstance(in_shot, str):
        in_shot = [in_shot.strip()] if in_shot.strip() else []
    elif isinstance(in_shot, list):
        in_shot = [_str(x) for x in in_shot if _str(x)]
    else:
        in_shot = []

    aesthetic_parts = [
        _str(data.get("emotion")),
        _str(vis.get("lighting")),
        _str(vis.get("color_grade")),
        "、".join(_str(t) for t in style_tags[:3] if t),
        "、".join(in_shot[:3]),
    ]

    camera_cut = _build_camera_cut(data, vis)
    sfx_text = _format_sfx(audio if isinstance(audio, dict) else {})

    return ShotPromptSix(
        subject="，".join(dict.fromkeys(subject_parts)),
        motion="，".join(dict.fromkeys(motion_parts)),
        environment=_str(vis.get("environment")),
        spatial=_spatial_from_entry(data),
        camera_cut=camera_cut,
        aesthetic="，".join(dict.fromkeys(p for p in aesthetic_parts if p)),
        audio=ShotAudio(
            voiceover_semantic=_str(vo.get("text")),
            tone_label=_str(vo.get("tone")),
            emotion=_str(data.get("emotion")),
            bgm=_str(audio.get("bgm")),
            ambient=_str(audio.get("ambient")),
            sfx=sfx_text,
        ),
    )


def merge_six_structure_only(primary: ShotPromptSix, fallback: ShotPromptSix) -> ShotPromptSix:
    """Adapted 优先；DNA 仅补结构字段（运镜/美学/BGM），不回灌内容字段。"""
    p = primary.model_dump()
    f = fallback.model_dump()

    p_audio = p.get("audio") or {}
    f_audio = f.get("audio") or {}
    f_delivery = f_audio.get("delivery") or {}
    p_delivery = p_audio.get("delivery") or {}
    merged_delivery = {
        k: (p_delivery.get(k) or f_delivery.get(k) or "")
        for k in ("volume", "pace", "breath", "pause", "stress", "tail")
    }

    merged_audio = {
        "voiceover_semantic": p_audio.get("voiceover_semantic") or "",
        "voiceover_performed": p_audio.get("voiceover_performed") or "",
        "tone_label": p_audio.get("tone_label") or f_audio.get("tone_label") or "",
        "emotion": p_audio.get("emotion") or f_audio.get("emotion") or "",
        "delivery": merged_delivery,
        "delivery_prompt": p_audio.get("delivery_prompt") or "",
        "bgm": p_audio.get("bgm") or f_audio.get("bgm") or "",
        "ambient": p_audio.get("ambient") or f_audio.get("ambient") or "",
        "sfx": p_audio.get("sfx") or f_audio.get("sfx") or "",
    }

    return ShotPromptSix(
        subject=p.get("subject") or "",
        motion=p.get("motion") or "",
        environment=p.get("environment") or "",
        spatial=list(p.get("spatial") or []),
        camera_cut=p.get("camera_cut") or f.get("camera_cut") or "",
        aesthetic=p.get("aesthetic") or f.get("aesthetic") or "",
        audio=ShotAudio.model_validate(merged_audio),
    )


def merge_six(primary: ShotPromptSix, fallback: ShotPromptSix) -> ShotPromptSix:
    """兼容旧调用：默认走 structure-only 合并。"""
    return merge_six_structure_only(primary, fallback)


def legacy_scene_to_six(scene: AdaptedScene) -> ShotPromptSix:
    """旧 visual_brief/camera/new_voiceover → six。"""
    camera_cut = (scene.camera or "").strip()
    return ShotPromptSix(
        motion="",
        environment=(scene.visual_brief or "").strip(),
        camera_cut=camera_cut,
        aesthetic=(scene.emotion or "").strip(),
        audio=ShotAudio(
            voiceover_semantic=(scene.new_voiceover or "").strip(),
            emotion=(scene.emotion or "").strip(),
        ),
    )


def match_omni_entry(
    video_dna: VideoDNA,
    start: float,
    end: float,
) -> Optional[TimelineEntry]:
    """按时间重叠找最匹配的 DNA timeline 条目。"""
    best: Optional[TimelineEntry] = None
    best_overlap = -1.0
    for entry in video_dna.timeline or []:
        s = float(entry.start)
        e = float(entry.end)
        if e <= s:
            continue
        overlap = min(end, e) - max(start, s)
        if overlap > best_overlap:
            best_overlap = overlap
            best = entry
    return best


def match_omni_entry_dict(
    timeline_entries: List[dict],
    scene_start: float,
    scene_end: float,
) -> Optional[dict]:
    best = None
    best_overlap = -1.0
    for entry in timeline_entries:
        s = float(entry.get("start") or 0)
        e = float(entry.get("end") or 0)
        if e <= s:
            continue
        overlap = min(scene_end, e) - max(scene_start, s)
        if overlap > best_overlap:
            best_overlap = overlap
            best = entry
    return best


def build_scene_six(
    scene: AdaptedScene,
    omni: Optional[Union[TimelineEntry, dict]] = None,
    global_tone: str = "",
) -> ShotPromptSix:
    """合并 adapted + DNA + legacy，返回最终六要素。"""
    has_six_content = bool(
        scene.six
        and (
            scene.six.subject
            or scene.six.motion
            or scene.six.environment
            or scene.six.audio.voiceover_semantic
        )
    )
    primary = scene.six if has_six_content else legacy_scene_to_six(scene)

    fallback = dna_entry_to_six(omni)
    merged = merge_six_structure_only(primary, fallback)

    if not merged.subject:
        merged.subject = "参考图1产品"
    if not merged.motion:
        intent = (scene.shot_intent or "").strip()
        if intent:
            merged.motion = intent
        elif merged.audio.voiceover_semantic:
            merged.motion = "自然展示参考图1产品"

    if not merged.audio.tone_label and global_tone:
        merged.audio.tone_label = global_tone
    if not merged.audio.emotion and scene.emotion:
        merged.audio.emotion = scene.emotion

    return merged
