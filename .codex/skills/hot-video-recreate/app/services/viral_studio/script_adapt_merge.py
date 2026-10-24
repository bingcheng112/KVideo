"""Pass B：B1/B2 结果合并与口播 segment 对齐。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.viral_studio.schemas import (
    AdaptedScene,
    AdaptedScript,
    BeatPlanEntry,
    GlobalConsistency,
    ReferenceRole,
    VideoDNA,
    VoiceoverSegment,
)
from app.services.viral_studio.voiceover_uniqueness import normalize_vo_text


def _timeline_scene_count(video_dna: VideoDNA) -> int:
    timeline = video_dna.timeline or []
    return max(len(timeline), 1)


def _timeline_entry(video_dna: VideoDNA, index: int):
    timeline = video_dna.timeline or []
    if 0 <= index < len(timeline):
        return timeline[index]
    return None


def align_voiceover_segments(
    segments: List[VoiceoverSegment],
    video_dna: VideoDNA,
    beat_plan: Optional[List[BeatPlanEntry]] = None,
) -> List[VoiceoverSegment]:
    """镜数与 DNA timeline 对齐；不足补空，多余截断。"""
    n = _timeline_scene_count(video_dna)
    by_id: Dict[int, VoiceoverSegment] = {}
    for seg in segments or []:
        sid = int(seg.scene_id or 0)
        if sid > 0:
            by_id[sid] = seg

    out: List[VoiceoverSegment] = []
    bp = beat_plan or []
    for i in range(n):
        sid = i + 1
        entry = _timeline_entry(video_dna, i)
        start = float(entry.start if entry else 0)
        end = float(entry.end if entry else 0)
        existing = by_id.get(sid)
        goal = ""
        if i < len(bp):
            goal = (bp[i].voiceover_goal or "").strip()
        elif existing:
            goal = (existing.voiceover_goal or "").strip()

        if existing:
            out.append(
                VoiceoverSegment(
                    scene_id=sid,
                    start_sec=float(existing.start_sec or start),
                    end_sec=float(existing.end_sec or end),
                    text=(existing.text or "").strip(),
                    voiceover_goal=goal or (existing.voiceover_goal or "").strip(),
                )
            )
        else:
            out.append(
                VoiceoverSegment(
                    scene_id=sid,
                    start_sec=start,
                    end_sec=end,
                    text="",
                    voiceover_goal=goal,
                )
            )
    return out


def find_duplicate_segment_scene_ids(segments: List[VoiceoverSegment]) -> List[int]:
    """segment 层口播重复检测（normalize 后 strict equal）。"""
    seen: Dict[str, int] = {}
    duplicates: List[int] = []
    for seg in segments or []:
        vo = normalize_vo_text(seg.text or "")
        if not vo:
            continue
        sid = int(seg.scene_id or 0)
        if vo in seen:
            if sid and sid not in duplicates:
                duplicates.append(sid)
        else:
            seen[vo] = sid
    return duplicates


def empty_voiceover_segments(video_dna: VideoDNA) -> List[VoiceoverSegment]:
    """NONE 模式：全镜空口播 segment。"""
    n = _timeline_scene_count(video_dna)
    out: List[VoiceoverSegment] = []
    for i in range(n):
        entry = _timeline_entry(video_dna, i)
        start = float(entry.start if entry else 0)
        end = float(entry.end if entry else 0)
        out.append(
            VoiceoverSegment(
                scene_id=i + 1,
                start_sec=start,
                end_sec=end,
                text="",
                voiceover_goal="",
            )
        )
    return out


def apply_voiceover_segments_to_script(script: AdaptedScript) -> AdaptedScript:
    """将 voiceover_segments 强制写入 adapted_script 口播字段。"""
    seg_by_id = {int(s.scene_id or 0): s for s in (script.voiceover_segments or [])}
    for scene in script.adapted_script or []:
        sid = int(scene.scene_id or 0)
        seg = seg_by_id.get(sid)
        text = (seg.text if seg else "") or ""
        scene.new_voiceover = text
        if scene.six:
            scene.six.audio.voiceover_semantic = text
    return script


def merge_b2_into_script(
    *,
    b1_partial: AdaptedScript,
    b2_data: Dict[str, Any],
    video_dna: VideoDNA,
) -> AdaptedScript:
    """合并 B1 口播规划 + B2 画面输出为完整 AdaptedScript。"""
    segments = align_voiceover_segments(
        b1_partial.voiceover_segments or [],
        video_dna,
        b1_partial.beat_plan,
    )

    b2_scenes_raw = b2_data.get("adapted_script") or []
    b2_by_id: Dict[int, dict] = {}
    for item in b2_scenes_raw:
        if isinstance(item, dict):
            try:
                b2_by_id[int(item.get("scene_id") or 0)] = item
            except (TypeError, ValueError):
                continue

    n = _timeline_scene_count(video_dna)
    merged_scenes: List[AdaptedScene] = []
    for i in range(n):
        sid = i + 1
        entry = _timeline_entry(video_dna, i)
        start = float(entry.start if entry else 0)
        end = float(entry.end if entry else 0)
        beat_role = (entry.beat_role if entry else "") or ""
        emotion = (entry.emotion if entry else "") or ""

        seg = next((s for s in segments if s.scene_id == sid), None)
        vo_text = (seg.text if seg else "") or ""

        raw = b2_by_id.get(sid) or {}
        scene = AdaptedScene.model_validate(
            {
                "scene_id": sid,
                "time_range": f"{start:g}-{end:g}s",
                "start_sec": start,
                "end_sec": end,
                "beat_role": raw.get("beat_role") or beat_role,
                "emotion": raw.get("emotion") or emotion,
                "shot_intent": raw.get("shot_intent") or "",
                "new_voiceover": vo_text,
                "visual_brief": raw.get("visual_brief") or "",
                "camera": raw.get("camera") or "",
                "must_show": raw.get("must_show") or [],
                "continuity_from_prev": raw.get("continuity_from_prev"),
                "six": raw.get("six") or {},
            }
        )
        if scene.six:
            scene.six.audio.voiceover_semantic = vo_text
        merged_scenes.append(scene)

    gc_raw = b2_data.get("global_consistency") or {}
    gc = GlobalConsistency.model_validate(gc_raw if isinstance(gc_raw, dict) else {})

    roles_raw = b2_data.get("reference_roles") or []
    roles: List[ReferenceRole] = []
    for item in roles_raw:
        if isinstance(item, dict):
            roles.append(ReferenceRole.model_validate(item))

    return AdaptedScript(
        adapted_script=merged_scenes,
        global_consistency=gc,
        inferred_product=b1_partial.inferred_product,
        source_product=b1_partial.source_product,
        beat_plan=b1_partial.beat_plan,
        full_voiceover=b1_partial.full_voiceover or "",
        voiceover_segments=segments,
        reference_roles=roles or b1_partial.reference_roles,
    )
