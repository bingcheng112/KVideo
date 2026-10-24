"""Pass B1：口播规划 prompt（先于分镜）。"""
from __future__ import annotations

from typing import Optional

from app.services.viral_studio.content_profile import ContentProfile, VoiceoverMode
from app.services.viral_studio.prompts.adapt import (
    PRESERVE_MODE_NOTE,
    REWRITE_MODE_NOTE,
    _profile_block,
)

ADAPT_VOICEOVER_SYSTEM = """你是爆款短视频口播迁移专家。你将根据「参考视频 DNA」、「产品参考图」与「新产品信息」，**仅规划口播与 beat_plan**，不输出画面 six。

任务：
1. 镜数须与 DNA timeline 一致，不得合并多镜
2. 保留原片 copy_framework 结构与 rhythm（每镜时长对齐 timeline ±0.5s）
3. **口播风格继承（默认 preserve）**：原片口播仅作风格参考；按新产品卖点重写；禁止照搬原片品牌/品类专有词
4. 先输出 beat_plan（每镜唯一 voiceover_goal），再输出 voiceover_segments 与 full_voiceover
5. **全片任意两镜 text 不得完全相同**（normalize 后 strict equal）；同卖点多镜须不同表述或留空
6. 句长与时长：≤2s 留空或 ≤8 字；2–4s 8–15 字；4–8s 15–25 字；>8s 25–35 字；装不下则留空（纯视觉镜）
7. full_voiceover 为全片连读稿（segments 按时间顺序拼接，镜间用空格；纯视觉镜跳过）
8. 若未提供产品名称/卖点，先从参考图识别写入 inferred_product
8b. 根据产品参考图判断 inferred_product.product_text_heavy（bool）与 product_text_heavy_reason：包装/说明书/密密麻麻卖点字 → true；仅 Logo 或少量品名 → false
9. 须输出 source_product：原片品类与关键词（供 must_avoid）
10. voiceover_segments 每项须含 scene_id、start_sec、end_sec、text、voiceover_goal，与 beat_plan 一一对应

输出唯一 JSON：
{
  "inferred_product": {
    "name": "从产品图识别的名称",
    "category": "品类",
    "selling_points": ["卖点1", "卖点2"],
    "visual_traits": "外观特征",
    "product_text_heavy": false,
    "product_text_heavy_reason": "仅有品名 Logo，文字很少"
  },
  "source_product": {
    "category": "原片品类",
    "keywords": ["原片品牌或品类词"]
  },
  "full_voiceover": "整段口播连读稿",
  "voiceover_segments": [
    {
      "scene_id": 1,
      "start_sec": 0,
      "end_sec": 3,
      "text": "该镜口播（可空）",
      "voiceover_goal": "本镜独有口播意图"
    }
  ],
  "beat_plan": [
    {
      "scene_id": 1,
      "beat_role": "黄金3秒钩子",
      "primary_selling_point": "卖点1",
      "display_action": "手持展示整体",
      "reference_image": "参考图1",
      "voiceover_goal": "本镜独有口播意图",
      "must_avoid": ["原片品牌词"]
    }
  ]
}

禁止 Markdown 代码块；禁止在 JSON 外输出说明。"""


def build_adapt_voiceover_user_text(
    product_name: str,
    product_info: str,
    dna_json: str,
    *,
    copy_mode: str = "preserve",
    genre: str = "",
    profile: Optional[ContentProfile] = None,
    product_image_count: int = 1,
    forbidden_terms_hint: str = "",
    target_engine: str = "seedance",
) -> str:
    name = (product_name or "").strip() or "（未提供，请从产品参考图识别）"
    info = (product_info or "").strip() or "（未提供，请从产品参考图总结卖点与使用场景）"
    genre_line = (genre or "").strip() or "（见 DNA meta.genre）"
    mode = (copy_mode or "preserve").strip().lower()
    mode_note = REWRITE_MODE_NOTE if mode == "rewrite" else PRESERVE_MODE_NOTE
    profile_block = _profile_block(profile)

    img_count = max(1, int(product_image_count or 1))
    img_line = f"共上传 {img_count} 张产品参考图，顺序对应参考图1"
    if img_count > 1:
        img_line += f"至参考图{img_count}"
    img_line += "。\n"

    forbidden_block = ""
    if forbidden_terms_hint:
        forbidden_block = f"\n【原片禁用词（must_avoid 须包含）】{forbidden_terms_hint}\n"

    engine_note = ""
    if (target_engine or "").strip().lower() == "happyhorse":
        engine_note = "\n【Happyhorse】每镜 text 控制在 1–2 句，利于口型同步。\n"

    off_screen_note = ""
    if profile and profile.voiceover_mode == VoiceoverMode.OFF_SCREEN:
        off_screen_note = "\n【画外音】口播为旁白，按卖点迁移；无人物出镜假设。\n"

    return f"""产品名称：{name}

产品信息：
{info}

原片类型（genre）：{genre_line}
{img_line}{profile_block}{forbidden_block}{engine_note}{off_screen_note}
{mode_note}

参考视频 DNA（JSON）：
{dna_json}

请生成口播规划 JSON：先 beat_plan，再 voiceover_segments 与 full_voiceover；镜数与 DNA timeline 一致；全片口播不得重复。"""
