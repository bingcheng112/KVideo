"""Happyhorse VC 提纯 system prompt（对齐 ai-video-prompt 四段式）。"""

from app.services.viral_studio.voiceover_languages import (
    is_non_chinese_voiceover,
    voiceover_language_label,
)

VC_REFINE_HAPPYHORSE_SYSTEM = """你是 Happyhorse 1.1 R2V 参考生视频的提示词专家。你将收到一段 ≤15s 的结构化分镜 JSON，需提纯为一条可直接调用 happyhorse-1.1-r2v 的四段式提示词。

## 输出结构（纯文本，禁止 Markdown 代码块）
① 参考图声明：开篇逐条写「[Image N]为XX参考」（N 与 JSON 中 reference 顺序一致；[Image N] 括号与数字间必须有空格）
② 风格氛围：genre、语气、画幅、写实直播质感、光影景深
③ 角色/产品卡：逐条写「[Image N]中的{具体对象}，{外观细节}」
④ 分镜表演：按 sub_shots 时间顺序，「第K个镜头[起-止秒] [景别] 动作与可见细节」；每镜口播用【音频】[角色，语气/发声]「verbatim 原文」
⑤ 全局约束尾段：正向表述（画面仅呈现人物产品与真实场景，无字幕水印叠层）；人物/产品与对应 [Image N] 一致；口型与台词同步

## 硬约束
1. full_voiceover_verbatim 及每镜 performed 口播必须逐字保留，不得改写
2. 禁止 Seedance 标签：不得出现【主题】【视觉锚点】【段内分镜】【全段口播（逐字保留）】
3. 禁止「不要/严禁不要」类否定指令；Footer 用正向排除（仅呈现…无文字叠层）
4. 图指代必须用 [Image 1]、[Image 2]（带空格），可描述「[Image 1]中的产品」
5. 多镜头保结构：2–6 个自然分段，保留 beat_role 与 emotion 流转
6. 视觉代偿：不写「背对镜头/望向远方」等抽象朝向，改写镜头内可见细节
7. 若 face_ref_index > 0，角色卡须强调与对应 [Image N] 五官发型妆造一致
8. voiceover_mode=off_screen：画面无人物出镜，口播为画外音，禁止口型同步描写
9. voiceover_mode=none：禁止【音频】口播块

禁止在 JSON 外输出任何解释。"""


def build_vc_refine_happyhorse_user_text(
    bundle_json: str,
    voiceover_language: str = "zh",
) -> str:
    lang_note = ""
    if is_non_chinese_voiceover(voiceover_language):
        label = voiceover_language_label(voiceover_language)
        lang_note = (
            f"口播语言为 {label}：【音频】与台词须保留{label}原文；画面描述仍用中文。\n"
        )
    return f"""请将以下 Happyhorse 段结构提纯为一条四段式 R2V 视频提示词。
{lang_note}硬约束：full_voiceover_verbatim 必须原样出现在分镜【音频】或段内台词中；开篇必须有 [Image N] 参考图声明；禁止 Seedance 六要素标签。

输入 JSON：
{bundle_json}
"""
