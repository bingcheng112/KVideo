"""单镜视觉 LLM 修复 prompt（口播锁定，仅改画面）。"""
from __future__ import annotations

import json
from typing import Any, List

from app.services.viral_studio.schemas import AdaptedScene, BeatPlanEntry, InferredProduct

SCENE_VISUAL_FIX_SYSTEM = """你是短视频分镜修复专家。口播已锁定，你**仅修复画面**：shot_intent 与 six 六要素。

须满足：
1. 体现 primary_selling_point 与 display_action
2. 不含 forbidden 中的原片品类词
3. subject/motion/spatial 与 locked_voiceover 语义一致（有口播时）
4. 保留 beat_role 与 emotion；camera_cut/aesthetic/sfx 尽量继承原输入
5. **禁止修改口播**：不得输出 new_voiceover / voiceover_semantic

输出唯一 JSON：
{
  "shot_intent": "画面意图",
  "six": {
    "subject": "参考图1产品",
    "motion": "展示动作",
    "environment": "场景",
    "spatial": ["空间关系"],
    "camera_cut": "继承原 six.camera_cut",
    "aesthetic": "继承原 six.aesthetic",
    "audio": {
      "tone_label": "继承",
      "emotion": "继承",
      "bgm": "继承或空",
      "ambient": "继承或空",
      "sfx": "继承或空"
    }
  }
}

禁止 Markdown；禁止输出说明。"""


def build_scene_visual_fix_user_text(
    scene: AdaptedScene,
    beat: BeatPlanEntry,
    inferred: InferredProduct | None,
    forbidden_terms: list[str],
    *,
    locked_voiceover: str = "",
    scene_duration_sec: float = 0.0,
) -> str:
    inferred_json = json.dumps(
        inferred.model_dump() if inferred else {},
        ensure_ascii=False,
    )
    scene_json = json.dumps(scene.model_dump(), ensure_ascii=False)
    beat_json = json.dumps(beat.model_dump(), ensure_ascii=False)
    forbidden = "、".join(forbidden_terms[:20]) if forbidden_terms else "无"
    dur = scene_duration_sec
    if dur <= 0 and scene.end_sec and scene.start_sec:
        dur = float(scene.end_sec) - float(scene.start_sec)
    locked = (locked_voiceover or "").strip() or "（本镜无口播，纯视觉）"
    return f"""请修复以下分镜画面（口播不可改）。

locked_voiceover（只读）：{locked}

beat_plan：
{beat_json}

inferred_product：
{inferred_json}

forbidden_terms：{forbidden}

本镜时长（秒）：{dur:.1f}

当前分镜（有问题）：
{scene_json}

请输出修复后的 JSON（仅 shot_intent + six）。"""
