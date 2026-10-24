"""Pass B：脚本连贯性校验与 beat_plan 兜底。"""
from __future__ import annotations

from typing import List, Optional, Tuple

from app.services.viral_studio.product_profile import infer_category_distance
from app.services.viral_studio.schemas import (
    AdaptedScene,
    AdaptedScript,
    BeatPlanEntry,
    CoherenceReport,
    InferredProduct,
    SourceProductProfile,
    VideoDNA,
)
from app.services.viral_studio.source_term_sanitize import (
    contains_forbidden,
    has_motion_conflict,
    sanitize_scene_content,
)
from app.services.viral_studio.voice_delivery_rules import build_delivery_prompt
from app.services.viral_studio.voiceover_uniqueness import find_duplicate_voiceover_scene_ids

_VOICEOVER_GOAL_TEMPLATES = (
    "清单体钩子，介绍产品名与核心卖点",
    "讲外观设计或包装细节",
    "讲整体版型或使用场景",
    "讲材质肤感或工艺",
    "讲舒适功能或科技成分",
    "讲细节设计或点缀",
    "动态演示产品特性（短承接句或留空）",
    "引导下单或品牌收尾",
)


def _voiceover_goal_for_scene(
    scene: AdaptedScene,
    index: int,
    selling_point: str,
) -> str:
    role = (scene.beat_role or "").strip()
    if "钩子" in role or index == 0:
        return f"清单体钩子，安利{selling_point or '产品'}"
    if "CTA" in role.upper() or "收尾" in role:
        return "引导下单或品牌收尾，急促诱导"
    template = _VOICEOVER_GOAL_TEMPLATES[index % len(_VOICEOVER_GOAL_TEMPLATES)]
    intent = (scene.shot_intent or "").strip()
    if intent:
        return f"{template}（画面：{intent[:24]}）"
    return template


def _selling_points(inferred: Optional[InferredProduct]) -> List[str]:
    if not inferred:
        return ["产品核心卖点"]
    points = [p.strip() for p in (inferred.selling_points or []) if p and p.strip()]
    if points:
        return points
    if inferred.name:
        return [inferred.name]
    if inferred.category:
        return [inferred.category]
    return ["产品核心卖点"]


def build_beat_plan_fallback(
    script: AdaptedScript,
    video_dna: VideoDNA,
    inferred: Optional[InferredProduct],
) -> List[BeatPlanEntry]:
    """LLM 未输出 beat_plan 时，按 timeline 均分卖点。"""
    scenes = script.adapted_script or []
    if not scenes:
        timeline = video_dna.timeline or []
        points = _selling_points(inferred)
        plan: List[BeatPlanEntry] = []
        for i, entry in enumerate(timeline):
            pt = points[i % len(points)]
            temp_scene = AdaptedScene(beat_role=entry.beat_role or "", shot_intent=entry.shot_intent or "")
            plan.append(
                BeatPlanEntry(
                    scene_id=i + 1,
                    beat_role=entry.beat_role or "",
                    primary_selling_point=pt,
                    display_action="自然展示参考图1产品",
                    reference_image="参考图1",
                    voiceover_goal=_voiceover_goal_for_scene(temp_scene, i, pt),
                )
            )
        return plan

    points = _selling_points(inferred)
    plan = []
    for i, scene in enumerate(scenes):
        pt = points[i % len(points)]
        plan.append(
            BeatPlanEntry(
                scene_id=scene.scene_id or (i + 1),
                beat_role=scene.beat_role or "",
                primary_selling_point=pt,
                display_action=scene.shot_intent or "自然展示参考图1产品",
                reference_image="参考图1",
                voiceover_goal=_voiceover_goal_for_scene(scene, i, pt),
            )
        )
    return plan


def _beat_for_scene(script: AdaptedScript, scene: AdaptedScene) -> Optional[BeatPlanEntry]:
    sid = scene.scene_id
    for bp in script.beat_plan or []:
        if bp.scene_id == sid:
            return bp
    idx = script.adapted_script.index(scene) if scene in (script.adapted_script or []) else -1
    if 0 <= idx < len(script.beat_plan or []):
        return script.beat_plan[idx]
    return None


def _scene_visual_text(scene: AdaptedScene) -> str:
    parts: List[str] = []
    if scene.six:
        parts.extend(
            [
                scene.six.subject or "",
                scene.six.motion or "",
                scene.six.environment or "",
                " ".join(scene.six.spatial or []),
            ]
        )
    parts.append(scene.shot_intent or "")
    return " ".join(p for p in parts if p)


def _selling_point_covered(text: str, selling_point: str) -> bool:
    sp = (selling_point or "").strip()
    if not sp or len(sp) < 2:
        return True
    t = (text or "").strip()
    if not t:
        return False
    if sp in t:
        return True
    # 卖点前两字匹配
    if len(sp) >= 2 and sp[:2] in t:
        return True
    return False


def align_delivery_with_voiceover(scene: AdaptedScene, global_tone: str = "") -> None:
    """重建 delivery_prompt，避免场景描述与口播品类冲突。"""
    if not scene.six:
        return
    six = scene.six
    performed = (six.audio.voiceover_performed or six.audio.voiceover_semantic or scene.new_voiceover or "").strip()
    if not performed:
        six.audio.delivery_prompt = ""
        return
    env = (six.environment or scene.visual_brief or scene.shot_intent or "").strip()
    six.audio.delivery_prompt = build_delivery_prompt(
        environment=env,
        shot_intent=scene.shot_intent or "",
        emotion=six.audio.emotion or scene.emotion or "",
        tone_label=six.audio.tone_label or global_tone or "",
        performed=performed,
        delivery=six.audio.delivery.model_dump(),
    )


def _evaluate_scene_issues(
    scene: AdaptedScene,
    beat: Optional[BeatPlanEntry],
    forbidden_terms: List[str],
) -> List[str]:
    issues: List[str] = []
    vo = (scene.new_voiceover or "").strip()
    if scene.six and scene.six.audio.voiceover_semantic:
        vo = vo or scene.six.audio.voiceover_semantic

    hits = contains_forbidden(vo, forbidden_terms)
    hits.extend(contains_forbidden(_scene_visual_text(scene), forbidden_terms))
    if hits:
        issues.append(f"forbidden:{','.join(dict.fromkeys(hits))}")

    if beat and beat.primary_selling_point:
        combined = f"{vo} {scene.shot_intent or ''} {_scene_visual_text(scene)}"
        if not _selling_point_covered(combined, beat.primary_selling_point):
            issues.append(f"missing_selling_point:{beat.primary_selling_point}")

    if has_motion_conflict(vo, _scene_visual_text(scene)):
        issues.append("motion_conflict")

    return issues


def check_and_fix_script_coherence(
    script: AdaptedScript,
    video_dna: VideoDNA,
    source_profile: SourceProductProfile,
    forbidden_terms: List[str],
) -> Tuple[AdaptedScript, CoherenceReport]:
    """规则清洗 + 连贯性评估。"""
    inferred = script.inferred_product
    if not script.source_product:
        script.source_product = source_profile
    if not script.beat_plan:
        script.beat_plan = build_beat_plan_fallback(script, video_dna, inferred)

    fixes: List[str] = []
    failed_ids: List[int] = []
    global_tone = (script.global_consistency.tone or "").strip()
    category_distance = infer_category_distance(source_profile, inferred)

    for scene in script.adapted_script or []:
        scene_fixes = sanitize_scene_content(scene, forbidden_terms, inferred)
        fixes.extend(scene_fixes)

        if scene.six and scene.new_voiceover:
            if not scene.six.audio.voiceover_semantic:
                scene.six.audio.voiceover_semantic = scene.new_voiceover
            elif scene.six.audio.voiceover_semantic != scene.new_voiceover:
                scene.six.audio.voiceover_semantic = scene.new_voiceover

        align_delivery_with_voiceover(scene, global_tone)

        beat = _beat_for_scene(script, scene)
        issues = _evaluate_scene_issues(scene, beat, forbidden_terms)
        if issues:
            sid = scene.scene_id or 0
            if sid and sid not in failed_ids:
                failed_ids.append(sid)
            fixes.append(f"scene_{sid}:issues={';'.join(issues)}")

    # 全段卖点覆盖
    all_points = _selling_points(inferred)
    full_text = " ".join(
        (s.new_voiceover or "") + " " + (s.six.audio.voiceover_semantic if s.six else "")
        for s in (script.adapted_script or [])
    )
    for pt in all_points:
        if not _selling_point_covered(full_text, pt):
            fixes.append(f"segment_missing_selling_point:{pt}")

    for sid in find_duplicate_voiceover_scene_ids(script):
        if sid and sid not in failed_ids:
            failed_ids.append(sid)
        fixes.append(f"scene_{sid}:duplicate_voiceover")

    passed = len(failed_ids) == 0
    report = CoherenceReport(
        passed=passed,
        category_distance=category_distance,
        fixes_applied=fixes,
        failed_scene_ids=failed_ids,
    )
    script.coherence_report = report
    return script, report
