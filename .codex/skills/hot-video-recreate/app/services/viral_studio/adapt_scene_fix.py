"""批量 LLM 修复（coherence 失败；支持 visual-only 与 legacy 全量）。"""
from __future__ import annotations

import logging
from typing import Dict, List, Set, Tuple

from app.services.viral_studio.json_utils import parse_json_object
from app.services.viral_studio.omni_client import chat_completion_stream
from app.services.viral_studio.prompts.adapt_scenes_batch_fix import (
    SCENES_BATCH_FIX_SYSTEM,
    build_batch_fix_user_text,
)
from app.services.viral_studio.prompts.adapt_scenes_batch_visual_fix import (
    SCENES_BATCH_VISUAL_FIX_SYSTEM,
    build_batch_visual_fix_user_text,
)
from app.services.viral_studio.schemas import (
    AdaptedScene,
    AdaptedScript,
    BeatPlanEntry,
    CoherenceReport,
    InferredProduct,
    ShotPromptSix,
)
from app.services.viral_studio.script_coherence import _beat_for_scene, _evaluate_scene_issues
from app.services.viral_studio.source_term_sanitize import sanitize_scene_content
from app.services.viral_studio.voiceover_uniqueness import effective_voiceover

logger = logging.getLogger(__name__)

BATCH_FIX_REMARK = "viral-studio-adapt-scenes-batch-fix"


def _apply_fix_payload(scene: AdaptedScene, data: dict, *, visual_only: bool = False) -> None:
    if not visual_only:
        if "new_voiceover" in data:
            vo = str(data.get("new_voiceover") or "").strip()
            scene.new_voiceover = vo
        else:
            vo = (scene.new_voiceover or "").strip()
    else:
        vo = effective_voiceover(scene)

    intent = str(data.get("shot_intent") or "").strip()
    if intent:
        scene.shot_intent = intent
    six_raw = data.get("six")
    if isinstance(six_raw, dict):
        merged = scene.six.model_dump() if scene.six else {}
        audio_raw = six_raw.get("audio") or {}
        if isinstance(audio_raw, dict):
            merged_audio = merged.get("audio") or {}
            for k, v in audio_raw.items():
                if v is not None and k not in ("voiceover_semantic", "voiceover_performed", "delivery_prompt"):
                    merged_audio[k] = v
            if not visual_only:
                merged_audio.update(
                    {k: v for k, v in audio_raw.items() if v is not None and k in ("voiceover_semantic",)}
                )
            six_raw = {**six_raw, "audio": merged_audio}
        for key in ("subject", "motion", "environment", "camera_cut", "aesthetic"):
            if six_raw.get(key):
                merged[key] = six_raw[key]
        if six_raw.get("spatial"):
            merged["spatial"] = six_raw["spatial"]
        scene.six = ShotPromptSix.model_validate(merged)
        if not visual_only:
            sem = (scene.six.audio.voiceover_semantic or "").strip()
            if sem:
                scene.new_voiceover = sem
            elif "new_voiceover" in data or (
                isinstance(audio_raw, dict) and "voiceover_semantic" in audio_raw
            ):
                scene.six.audio.voiceover_semantic = ""
                scene.six.audio.voiceover_performed = ""
                scene.six.audio.delivery_prompt = ""
                scene.new_voiceover = ""


def filter_fix_targets(
    script: AdaptedScript,
    report: CoherenceReport,
    forbidden_terms: List[str],
    *,
    visual_only: bool = False,
) -> List[int]:
    """visual_only 时跳过仅因 duplicate_voiceover 入失败列表的镜。"""
    failed = list(report.failed_scene_ids or [])
    if not visual_only or not failed:
        return failed
    from app.services.viral_studio.voiceover_uniqueness import find_duplicate_voiceover_scene_ids

    dup_ids = set(find_duplicate_voiceover_scene_ids(script))
    out: List[int] = []
    for sid in failed:
        if sid in dup_ids:
            scene = next((s for s in (script.adapted_script or []) if s.scene_id == sid), None)
            if scene:
                beat = _beat_for_scene(script, scene)
                issues = _evaluate_scene_issues(scene, beat, forbidden_terms)
                if not issues:
                    continue
        out.append(sid)
    return out


def pick_fix_targets(
    script: AdaptedScript,
    report: CoherenceReport,
    forbidden_terms: List[str],
    *,
    already_retried: Set[int],
    visual_only: bool = False,
) -> List[int]:
    """选取本轮全部待修镜：优先尚未 retried 的；若均已 retried 则再修仍失败的镜。"""
    failed = filter_fix_targets(
        script, report, forbidden_terms, visual_only=visual_only
    )
    if not failed:
        return []
    never = [sid for sid in failed if sid not in already_retried]
    if never:
        return never
    return list(failed)


def _beat_or_fallback(
    script: AdaptedScript,
    scene: AdaptedScene,
    inferred: InferredProduct | None,
) -> BeatPlanEntry:
    beat = _beat_for_scene(script, scene)
    if beat:
        return beat
    return BeatPlanEntry(
        scene_id=scene.scene_id,
        beat_role=scene.beat_role or "",
        primary_selling_point=(
            inferred.selling_points[0]
            if inferred and inferred.selling_points
            else "产品卖点"
        ),
        display_action=scene.shot_intent or "展示参考图1产品",
    )


def _batch_max_tokens(n: int) -> int:
    return min(8192, 512 + max(1, n) * 600)


def _parse_fixes_map(raw: str) -> Dict[int, dict]:
    data = parse_json_object(raw)
    fixes_raw = data.get("fixes")
    if not isinstance(fixes_raw, list):
        raise ValueError("missing fixes array")
    fixes_by_id: Dict[int, dict] = {}
    for item in fixes_raw:
        if not isinstance(item, dict):
            continue
        sid_raw = item.get("scene_id")
        if sid_raw is None:
            continue
        fixes_by_id[int(sid_raw)] = item
    return fixes_by_id


def _apply_batch_fixes(
    script: AdaptedScript,
    batch: List[int],
    fixes_by_id: Dict[int, dict],
    *,
    forbidden_terms: List[str],
    report: CoherenceReport,
    visual_only: bool,
    retried_set: Set[int],
) -> List[int]:
    inferred = script.inferred_product
    retried: List[int] = []
    fix_tag = "batch_visual_fix" if visual_only else "batch_llm_fix"
    missing_tag = "batch_fix_missing"
    failed_tag = "batch_visual_fix_failed" if visual_only else "batch_llm_fix_failed"

    for sid in batch:
        scene = next((s for s in (script.adapted_script or []) if s.scene_id == sid), None)
        if not scene:
            report.fixes_applied.append(f"scene_{sid}:{missing_tag}")
            continue

        fix = fixes_by_id.get(sid)
        if not fix:
            report.fixes_applied.append(f"scene_{sid}:{missing_tag}")
            continue

        beat = _beat_or_fallback(script, scene, inferred)
        try:
            _apply_fix_payload(scene, fix, visual_only=visual_only)
            sanitize_scene_content(scene, forbidden_terms, inferred)
            issues = _evaluate_scene_issues(scene, beat, forbidden_terms)
            if not issues and sid in (report.failed_scene_ids or []):
                report.failed_scene_ids = [x for x in report.failed_scene_ids if x != sid]
            report.fixes_applied.append(f"scene_{sid}:{fix_tag}")
            retried.append(sid)
            retried_set.add(sid)
        except Exception as e:
            logger.warning("批量修镜写回失败 scene=%s visual_only=%s: %s", sid, visual_only, e)
            report.fixes_applied.append(f"scene_{sid}:{failed_tag}")

    report.scenes_retried = list(set((report.scenes_retried or []) + retried))
    return retried


async def fix_failed_scenes(
    user_id: str,
    *,
    target_url: str,
    model_name: str,
    script: AdaptedScript,
    forbidden_terms: List[str],
    report: CoherenceReport,
    visual_only: bool = False,
    already_retried: Set[int] | None = None,
) -> Tuple[AdaptedScript, int, Set[int]]:
    """对 failed_scene_ids 批量一次 LLM 修复；visual_only 时口播锁定。"""
    retried_set: Set[int] = set(already_retried or [])

    batch = pick_fix_targets(
        script,
        report,
        forbidden_terms,
        already_retried=retried_set,
        visual_only=visual_only,
    )
    if not batch:
        return script, 0, retried_set

    if visual_only:
        user_text = build_batch_visual_fix_user_text(script, batch, forbidden_terms)
        system = SCENES_BATCH_VISUAL_FIX_SYSTEM
    else:
        user_text = build_batch_fix_user_text(script, batch, forbidden_terms)
        system = SCENES_BATCH_FIX_SYSTEM

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]

    try:
        raw, _resp, total_cost, _bal = await chat_completion_stream(
            user_id,
            target_url=target_url,
            model_name=model_name,
            messages=messages,
            max_tokens=_batch_max_tokens(len(batch)),
            video_seconds=0,
            consumption_remark=BATCH_FIX_REMARK,
        )
        fixes_by_id = _parse_fixes_map(raw)
        _apply_batch_fixes(
            script,
            batch,
            fixes_by_id,
            forbidden_terms=forbidden_terms,
            report=report,
            visual_only=visual_only,
            retried_set=retried_set,
        )
    except Exception as e:
        logger.warning("批量修镜失败 visual_only=%s batch=%s: %s", visual_only, batch, e)
        report.fixes_applied.append("batch_fix_failed")
        return script, 0, retried_set

    report.passed = len(report.failed_scene_ids or []) == 0
    script.coherence_report = report
    return script, total_cost, retried_set
