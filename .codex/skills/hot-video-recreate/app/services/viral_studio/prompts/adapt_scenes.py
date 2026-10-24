"""Pass B2：分镜画面 prompt（口播已锁定）。"""
from __future__ import annotations

import json
from typing import List, Optional

from app.services.viral_studio.content_profile import ContentProfile, VoiceoverMode
from app.services.viral_studio.prompts.adapt import _presentation_block, _profile_block
from app.services.viral_studio.schemas import PresentationProfile, VoiceoverSegment

ADAPT_SCENES_SYSTEM = """你是爆款短视频分镜专家。口播已锁定，你**仅生成画面**：shot_intent 与 six 六要素。

任务：
1. 镜数须与输入 voiceover_segments 一致，不得合并
2. **禁止修改口播**：locked_voiceover 只读；输出 JSON 不得含 new_voiceover / voiceover_semantic
3. 每镜 six 须服务 beat_plan 的 display_action，且与 locked_voiceover 语义一致（有口播时）
4. 保留原片情绪曲线：beat_role、emotion 对齐 DNA
5. six.subject/motion/environment/spatial 须互相一致；不得沿用原片品类展示动作
6. six.camera_cut 继承 DNA 对应镜 visual.camera + camera_motion + edit.cut_type + transition_out
7. six.aesthetic 继承 DNA 对应镜 color_grade + in_shot_effects + style_tags
8. six.audio 仅写 tone_label、emotion、bgm、ambient、sfx（**不写 voiceover 字段**）
9. 多图指代：主产品「参考图1」；出镜人物「参考图{人脸序号}」（若有）
10. 产品图陈列道具（衣架/挂拍）不得写入 motion/spatial；展示形态继承 DNA
11. 须输出 global_consistency 与 reference_roles

输出唯一 JSON：
{
  "adapted_script": [
    {
      "scene_id": 1,
      "beat_role": "黄金3秒钩子",
      "emotion": "好奇",
      "shot_intent": "新产品画面意图",
      "visual_brief": "画面意图（兼容）",
      "camera": "运镜（兼容）",
      "must_show": ["参考图1产品完整露出"],
      "continuity_from_prev": null,
      "six": {
        "subject": "参考图1产品",
        "motion": "与 display_action 一致",
        "environment": "场景描述",
        "spatial": ["产品位于画面中央"],
        "camera_cut": "继承 DNA 运镜",
        "aesthetic": "继承 DNA 美学",
        "audio": {
          "tone_label": "继承 DNA tone",
          "emotion": "好奇",
          "bgm": "继承或空",
          "ambient": "继承或空",
          "sfx": "2.3秒处叮一声"
        }
      }
    }
  ],
  "global_consistency": {
    "character": "",
    "product_ref": "参考图1",
    "tone": "继承 DNA 全片语气"
  },
  "reference_roles": [
    {"index": 1, "role": "product", "label": "产品名称或外观"}
  ]
}

禁止 Markdown；禁止输出说明。"""


def build_adapt_scenes_user_text(
    dna_json: str,
    segments: List[VoiceoverSegment],
    beat_plan_json: str,
    inferred_json: str,
    *,
    profile: Optional[ContentProfile] = None,
    presentation: Optional[PresentationProfile] = None,
    presentation_json: str = "",
    character_summary: str = "",
    face_reference_image_url: str = "",
    presented_gender: str = "",
    product_image_count: int = 1,
    forbidden_terms_hint: str = "",
) -> str:
    seg_json = json.dumps(
        [s.model_dump() for s in segments],
        ensure_ascii=False,
    )
    profile_block = _profile_block(profile)
    pres_block = presentation_json.strip()
    if not pres_block and presentation and profile:
        pres_block = _presentation_block(profile, presentation)

    char_line = (character_summary or "").strip()
    pg = (presented_gender or "").strip().lower()
    char_block = ""
    if char_line or pg in ("female", "male") or (face_reference_image_url or "").strip():
        parts = []
        if char_line:
            parts.append(f"人物描述：{char_line}")
        if pg in ("female", "male"):
            parts.append(f"呈现性别：{'女性' if pg == 'female' else '男性'}")
        if (face_reference_image_url or "").strip():
            parts.append("最后一张图片为出镜人物参考")
        char_block = "\n【人物对齐】\n" + "\n".join(parts) + "\n"

    img_count = max(1, int(product_image_count or 1))
    img_line = f"共 {img_count} 张产品参考图。\n"

    forbidden_block = ""
    if forbidden_terms_hint:
        forbidden_block = f"\n【原片禁用词】{forbidden_terms_hint}\n"

    locked_note = ""
    if profile and profile.voiceover_mode == VoiceoverMode.NONE:
        locked_note = "\n【纯视觉】locked_voiceover 全为空；禁止生成任何口播相关字段。\n"
    else:
        locked_note = "\n【口播已锁定】voiceover_segments.text 为最终口播，画面须服务该口播，禁止改写。\n"

    return f"""{img_line}{profile_block}{pres_block}{char_block}{forbidden_block}{locked_note}
beat_plan：
{beat_plan_json}

inferred_product：
{inferred_json}

locked_voiceover（voiceover_segments，只读）：
{seg_json}

参考视频 DNA（JSON）：
{dna_json}

请生成画面分镜 JSON（adapted_script + global_consistency + reference_roles）；不得输出口播字段。"""
