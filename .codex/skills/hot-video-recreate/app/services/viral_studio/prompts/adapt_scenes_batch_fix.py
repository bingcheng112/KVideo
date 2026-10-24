"""多镜批量 LLM 修复 prompt（coherence 失败时，可改口播+画面）。"""
from __future__ import annotations

import json
from typing import Any, List

from app.services.viral_studio.schemas import AdaptedScript, BeatPlanEntry, InferredProduct
from app.services.viral_studio.script_coherence import _beat_for_scene, _evaluate_scene_issues
from app.services.viral_studio.voiceover_uniqueness import collect_used_voiceovers, scene_duration_sec

SCENES_BATCH_FIX_SYSTEM = """你是短视频脚本批量修复专家。你将收到多镜迁移失败的分镜数据，须逐镜重写口播与六要素，使其：

1. 体现 primary_selling_point 与 display_action
2. 不含 must_avoid / forbidden 中的原片品类词
3. 口播与 subject/motion/spatial 语义一致
4. 保留 beat_role 与 emotion 曲线；tone_label 继承原输入
5. 本镜口播不得与「已用口播列表」中任一句完全相同（normalize 后 strict equal）
6. 按 voiceover_goal + display_action 写新句；若无法新增信息则 voiceover_semantic 与 new_voiceover 留空（纯视觉镜）
7. 口播长度须适配本镜时长：≤2s 留空或 ≤8 字；2–4s 8–15 字；4–8s 15–25 字；>8s 25–35 字

输出唯一 JSON，fixes 长度须等于 failed_scenes 长度，每个 scene_id 出现且仅出现一次：
{
  "fixes": [
    {
      "scene_id": 1,
      "new_voiceover": "修复后口播（可空）",
      "shot_intent": "画面意图",
      "six": {
        "subject": "参考图1产品",
        "motion": "展示动作",
        "environment": "场景",
        "spatial": ["空间关系"],
        "camera_cut": "继承原 six.camera_cut",
        "aesthetic": "继承原 six.aesthetic",
        "audio": {
          "voiceover_semantic": "与 new_voiceover 相同（可空）",
          "tone_label": "继承",
          "emotion": "继承",
          "bgm": "继承或空",
          "ambient": "继承或空",
          "sfx": "继承或空"
        }
      }
    }
  ]
}

禁止 Markdown；禁止输出说明。"""


def _beat_or_fallback_for_prompt(
    script: AdaptedScript,
    scene_id: int,
    *,
    inferred: InferredProduct | None,
) -> BeatPlanEntry:
    scene = next((s for s in (script.adapted_script or []) if s.scene_id == scene_id), None)
    if not scene:
        return BeatPlanEntry(scene_id=scene_id, beat_role="", primary_selling_point="产品卖点", display_action="展示参考图1产品")
    beat = _beat_for_scene(script, scene)
    if beat:
        return beat
    return BeatPlanEntry(
        scene_id=scene_id,
        beat_role=scene.beat_role or "",
        primary_selling_point=(
            inferred.selling_points[0]
            if inferred and inferred.selling_points
            else "产品卖点"
        ),
        display_action=scene.shot_intent or "展示参考图1产品",
    )


def build_batch_fix_user_text(
    script: AdaptedScript,
    batch_scene_ids: List[int],
    forbidden_terms: list[str],
) -> str:
    inferred = script.inferred_product
    inferred_json = json.dumps(
        inferred.model_dump() if inferred else {},
        ensure_ascii=False,
    )
    beat_plan_json = json.dumps(
        [b.model_dump() for b in (script.beat_plan or [])],
        ensure_ascii=False,
    )
    forbidden = "、".join(forbidden_terms[:20]) if forbidden_terms else "无"

    failed_scenes: list[dict[str, Any]] = []
    for sid in batch_scene_ids:
        scene = next((s for s in (script.adapted_script or []) if s.scene_id == sid), None)
        if not scene:
            continue
        beat = _beat_or_fallback_for_prompt(script, sid, inferred=inferred)
        dur = scene_duration_sec(scene)
        if dur <= 0 and scene.end_sec and scene.start_sec:
            dur = float(scene.end_sec) - float(scene.start_sec)
        used = collect_used_voiceovers(script, exclude_scene_id=sid)
        issues = _evaluate_scene_issues(scene, beat, forbidden_terms)
        failed_scenes.append(
            {
                "scene_id": sid,
                "duration_sec": round(dur, 1),
                "beat": beat.model_dump(),
                "used_voiceovers": used,
                "issues_hint": issues,
                "scene": scene.model_dump(),
            }
        )

    failed_json = json.dumps(failed_scenes, ensure_ascii=False)
    return f"""请批量修复以下 {len(failed_scenes)} 镜分镜。

inferred_product：
{inferred_json}

beat_plan：
{beat_plan_json}

forbidden_terms：{forbidden}

failed_scenes（须逐镜修复，输出 fixes 数组）：
{failed_json}

请输出修复后的 JSON（fixes 数组）。"""
