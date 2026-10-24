"""Pass B：脚本迁移 prompt（结构继承 + 卖点驱动 + beat_plan）。"""
from __future__ import annotations

from typing import Optional

from app.services.viral_studio.content_profile import ContentProfile, VoiceoverMode
from app.services.viral_studio.schemas import PresentationProfile

ADAPT_SYSTEM = """你是爆款短视频创意迁移专家。你将根据「参考视频 DNA」、「产品参考图」与「新产品信息」，生成适配新产品的脚本。

任务：
1. 保留原片的 copy_framework 结构与 rhythm 节奏（每段时长对齐原 timeline ±0.5s）
2. 镜数须与 DNA timeline 基本一致，不得合并多镜为一镜
3. **口播风格继承（默认 preserve）**：原片口播仅作风格参考（钩子类型、句式节奏、语气 tone）；须按新产品卖点重写每镜口播，禁止照搬原片品牌/品类专有词；无口播则 voiceover_semantic 为空
4. **卖点-分镜映射**：先输出 beat_plan（每镜唯一 voiceover_goal），再写 adapted_script；一口播一镜一意；每镜口播须体现该镜卖点；口播、subject、motion、spatial 须互相一致、全段读下来流畅连贯
5. **口播规划（先于写 six）**：
   - Step1：读 DNA timeline，确定镜数 N、每镜 start_sec/end_sec、beat_role、display_action
   - Step2：beat_plan 每镜必须有**唯一** voiceover_goal（本镜口播意图，不得与其他镜相同）；同一卖点多镜演示时各镜表达角度须不同
   - Step3：adapted_script 落实 beat_plan；**全片任意两镜 voiceover_semantic 不得完全相同**；写完后自检全片口播无重复
   - 句长与时长：≤2s 留空或 ≤8 字；2–4s 8–15 字；4–8s 15–25 字；>8s 25–35 字；装不下则留空（纯视觉镜）
6. **多图指代**：参考图顺序与用户上传的产品图一致。主产品固定「参考图1」；若有多张产品图，参考图2…N 用于补充角度/背面/细节；six.subject 与 must_show 须按分镜意图选用对应图号。出镜人物（若有）用「参考图{人脸序号}」
7. **保留原片情绪曲线**：beat_role 与 DNA timeline 对齐；emotion 原则上保留；shot_intent 改写为新产品画面意图
8. **语言风格对齐 DNA**：遵循 meta.genre 与原片 voiceover.tone；仅原片为口播带货时才用素人分享口吻
9. 每镜必须输出完整 six（Seedance 六要素），主体/运动/环境/空间须服务 display_action，不得沿用原片品类展示动作
10. audio.voiceover_semantic 写语义口播（先不加表演标点）；audio.tone_label 继承 DNA 对应镜 voiceover.tone
11. six.camera_cut 须继承 DNA 对应镜 visual.camera + camera_motion + edit.cut_type + transition_out
12. six.aesthetic 须继承 DNA 对应镜 color_grade + in_shot_effects + style_tags
13. six.audio.sfx 须继承 DNA 对应镜 sfx + sfx_at_sec
14. 若未提供产品名称或卖点，须先从参考图识别品类、名称、外观、核心卖点，写入 inferred_product
14b. **产品图文字密度**：根据产品参考图判断 `inferred_product.product_text_heavy`（bool）与 `product_text_heavy_reason`（短句）。产品主体外可见文字区域占比高、多行说明/成分表/价签/密密麻麻卖点文案 → true；仅 Logo 或少量品名 → false。该字段供后续视频模型路由使用
15. 用户手填的名称/卖点仅作补充；与识图冲突时以识图+参考图为准
16. **人物对齐（仅当用户提供人像参考时）**：出镜人物以参考人像为准；口播人称/性别词与参考人像一致；six.subject 不得沿用原片异性人物描述
17. **参考图 vs 视频呈现**：产品参考图仅用于识别产品外观、卖点与图号指代（subject/must_show 写参考图N产品）；产品图中的摄影陈列道具（衣架、模特架、挂拍构图）**不得**写入 six.motion、spatial、shot_intent、display_action。视频人物动作与展示形态须继承 DNA timeline（原片手持/对镜则新产品也为手持参考图N产品），禁止照搬产品图里的挂衣架构图
18. 须输出 source_product：从 DNA 推断的原片品类与关键词（供 must_avoid）
19. 顶层必须输出 reference_roles 数组（1-based index 与参考图顺序一致）

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
  "beat_plan": [
    {
      "scene_id": 1,
      "beat_role": "黄金3秒钩子",
      "primary_selling_point": "卖点1",
      "display_action": "手持展示整体",
      "reference_image": "参考图1",
      "voiceover_goal": "本镜独有口播意图（全片唯一，不得与其他镜 voiceover_goal 相同）",
      "must_avoid": ["原片品牌词"]
    }
  ],
  "adapted_script": [
    {
      "scene_id": 1,
      "time_range": "0-5s",
      "start_sec": 0,
      "end_sec": 5,
      "beat_role": "黄金3秒钩子",
      "emotion": "好奇",
      "shot_intent": "新产品画面意图",
      "new_voiceover": "按卖点重写的口播",
      "visual_brief": "画面意图（兼容）",
      "camera": "运镜（兼容）",
      "must_show": ["参考图1产品完整露出"],
      "continuity_from_prev": null,
      "six": {
        "subject": "参考图1产品",
        "motion": "与 display_action 一致的产品展示动作",
        "environment": "场景描述",
        "spatial": ["产品位于画面中央"],
        "camera_cut": "继承 DNA 运镜切镜",
        "aesthetic": "继承 DNA 美学",
        "audio": {
          "voiceover_semantic": "按卖点重写的口播",
          "tone_label": "继承 DNA voiceover.tone",
          "emotion": "好奇",
          "bgm": "继承 DNA 或空",
          "ambient": "继承 DNA 或空",
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

禁止 Markdown 代码块；禁止在 JSON 外输出说明。"""

REWRITE_MODE_NOTE = """
【创意改写模式 copy_mode=rewrite】
口播、画面意图、beat 结构可更自由调整；仍须输出 beat_plan，每镜围绕 primary_selling_point；禁止照搬原片品类词。
"""

PRESERVE_MODE_NOTE = """
【口播风格保留 copy_mode=preserve】
保留原片钩子类型、句式节奏与 tone；按 beat_plan 与 inferred_product 重写每镜口播与画面。
禁止保留原片品牌名、品类专有词、与原品类绑定的动作词（如鞋类「上脚/鞋头」、内衣类「杯型」等若属于原片而非新产品则不得保留）。
全段口播须流畅连贯，镜间自然承接；**全片任意两镜口播句子不得完全相同**（同卖点多镜须不同表述或后续镜留空）。
"""


def _profile_block(profile: Optional[ContentProfile]) -> str:
    if profile is None:
        return ""
    if profile.voiceover_mode == VoiceoverMode.NONE:
        return (
            "\n【原片无口播、无人物出镜】禁止生成任何口播字段（voiceover_semantic/new_voiceover 为空）；"
            "six.subject 不得含博主/人物；global_consistency.character 必须为空；"
            "禁止描写人物动作与人物空间关系。\n"
        )
    if profile.voiceover_mode == VoiceoverMode.OFF_SCREEN:
        return (
            "\n【原片画外音口播、无人物出镜】须按新产品卖点迁移口播；"
            "six.subject 仅写参考图N产品/场景（按分镜选图）；global_consistency.character 必须为空；"
            "禁止人物动作描写（举起、表情等），只写产品/场景运动。\n"
        )
    return ""


def _presentation_block(
    profile: Optional[ContentProfile],
    presentation: Optional[PresentationProfile],
) -> str:
    if presentation is None or profile is None:
        return ""
    if not profile.requires_generic_person and presentation.mode == "off_screen":
        return ""
    gc_char = presentation.generic_character or "年轻博主，自然五官，非特定名人"
    return (
        f"\n【呈现继承】\n"
        f"- presentation_mode={presentation.mode}，display_style={presentation.display_style or '产品展示'}\n"
        f"- 跨品类仅换产品/卖点；禁止改变展示形态（手持↔悬挂）\n"
        f"- 产品图若有衣架/挂拍，仅作外观参考；motion/spatial 须写 DNA 手持/对镜动作，禁止写衣架\n"
        f"- 无 face_ref 时：global_consistency.character={gc_char}\n"
        f"- six.subject 须含参考图1产品 + 原片呈现动作（手持/对镜/手部/博主）\n"
        f"- 全片口播不得重复；同卖点多镜须不同表述角度\n"
    )


def build_adapt_user_text(
    product_name: str,
    product_info: str,
    dna_json: str,
    *,
    copy_mode: str = "preserve",
    genre: str = "",
    character_summary: str = "",
    face_reference_image_url: str = "",
    presented_gender: str = "",
    profile: Optional[ContentProfile] = None,
    product_image_count: int = 1,
    forbidden_terms_hint: str = "",
    presentation_json: str = "",
) -> str:
    name = (product_name or "").strip() or "（未提供，请从产品参考图识别）"
    info = (product_info or "").strip() or "（未提供，请从产品参考图总结卖点与使用场景）"
    genre_line = (genre or "").strip() or "（见 DNA meta.genre）"
    char_line = (character_summary or "").strip()
    pg = (presented_gender or "").strip().lower()
    has_face_ref = bool((face_reference_image_url or "").strip()) or bool(char_line) or pg in (
        "female",
        "male",
    )

    char_parts: list[str] = []
    if char_line:
        char_parts.append(f"人物描述（写入 global_consistency.character）：{char_line}")
    if pg in ("female", "male"):
        label = "女性" if pg == "female" else "男性"
        char_parts.append(f"参考人像呈现性别：{label}（presented_gender={pg}）")
    if (face_reference_image_url or "").strip():
        char_parts.append(
            "用户消息中最后一张图片为出镜人物参考；口播人称/称呼/性别词与 six.subject 须与此人物一致"
        )
    char_block = ""
    if char_parts:
        char_block = "\n【人物对齐】\n" + "\n".join(char_parts) + "\n"

    mode = (copy_mode or "preserve").strip().lower()
    mode_note = REWRITE_MODE_NOTE if mode == "rewrite" else PRESERVE_MODE_NOTE
    profile_block = _profile_block(profile)
    presentation_block = presentation_json.strip()
    if not presentation_block and profile and profile.requires_generic_person:
        presentation_block = (
            f"\n【呈现继承】\n"
            f"- presentation_mode={profile.presentation_mode}；须保留原片展示形态\n"
            f"- 无 face_ref 时写入 generic 虚拟博主到 global_consistency.character\n"
            f"- six.subject 须含参考图1产品 + 原片呈现动作\n"
        )
    img_count = max(1, int(product_image_count or 1))
    img_line = f"共上传 {img_count} 张产品参考图，顺序对应参考图1"
    if img_count > 1:
        img_line += f"至参考图{img_count}"
    img_line += "。\n"

    forbidden_block = ""
    if forbidden_terms_hint:
        forbidden_block = f"\n【原片禁用词（must_avoid 须包含）】{forbidden_terms_hint}\n"

    return f"""产品名称：{name}

产品信息：
{info}

原片类型（genre）：{genre_line}
{img_line}{profile_block}{presentation_block}{char_block}{forbidden_block}
{mode_note}

参考视频 DNA（JSON）：
{dna_json}

请生成适配该产品的 migrated script JSON。先输出 beat_plan 再输出 adapted_script；保留 DNA 每镜 beat_role 与 emotion 曲线；每镜输出完整 six 六要素；输出 inferred_product 与 source_product。"""
