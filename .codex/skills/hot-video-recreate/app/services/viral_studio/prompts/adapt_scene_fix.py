"""单镜 LLM 修复 prompt（coherence 失败时）。"""

from __future__ import annotations



import json

from typing import Any, List



from app.services.viral_studio.schemas import AdaptedScene, BeatPlanEntry, InferredProduct



SCENE_FIX_SYSTEM = """你是短视频脚本修复专家。你将收到一镜迁移失败的分镜数据，须重写该镜口播与六要素，使其：

1. 体现 primary_selling_point 与 display_action

2. 不含 must_avoid / forbidden 中的原片品类词

3. 口播与 subject/motion/spatial 语义一致

4. 保留 beat_role 与 emotion 曲线；tone_label 继承原输入

5. 本镜口播不得与「已用口播列表」中任一句完全相同（normalize 后 strict equal）

6. 按 voiceover_goal + display_action 写新句；若无法新增信息则 voiceover_semantic 与 new_voiceover 留空（纯视觉镜）

7. 口播长度须适配本镜时长：≤2s 留空或 ≤8 字；2–4s 8–15 字；4–8s 15–25 字；>8s 25–35 字



输出唯一 JSON：

{

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



禁止 Markdown；禁止输出说明。"""





def build_scene_fix_user_text(

    scene: AdaptedScene,

    beat: BeatPlanEntry,

    inferred: InferredProduct | None,

    forbidden_terms: list[str],

    *,

    used_voiceovers: List[dict[str, Any]] | None = None,

    scene_duration_sec: float = 0.0,

) -> str:

    inferred_json = json.dumps(

        inferred.model_dump() if inferred else {},

        ensure_ascii=False,

    )

    scene_json = json.dumps(scene.model_dump(), ensure_ascii=False)

    beat_json = json.dumps(beat.model_dump(), ensure_ascii=False)

    forbidden = "、".join(forbidden_terms[:20]) if forbidden_terms else "无"

    used = used_voiceovers or []

    used_json = json.dumps(used, ensure_ascii=False)

    dur = scene_duration_sec

    if dur <= 0 and scene.end_sec and scene.start_sec:

        dur = float(scene.end_sec) - float(scene.start_sec)

    return f"""请修复以下分镜。



beat_plan：

{beat_json}



inferred_product：

{inferred_json}



forbidden_terms：{forbidden}



本镜时长（秒）：{dur:.1f}



已用口播（本镜不得与以下任一句重复）：

{used_json}



当前分镜（有问题）：

{scene_json}



请输出修复后的 JSON。"""

