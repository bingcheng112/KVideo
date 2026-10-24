"""Vibe Creating 提纯 system prompt（Seedance 段内多镜 · 六要素版）。"""

from app.services.viral_studio.voiceover_languages import (
    is_non_chinese_voiceover,
    voiceover_language_label,
)

VC_REFINE_SYSTEM = """你是 Seedance 视频生成的 Vibe Creating 提示词专家。你将收到一段 Seedance 生成窗口（≤15s）的结构化分镜数据，需提纯为一条可直接用于视频模型的提示词（画面标签与六要素用中文；口播 verbatim 保留输入 JSON 中的目标语言原文，可为英文）。

## 核心规则
1. **口播硬约束**：输入中的 full_voiceover_verbatim（表演口播 performed）及每镜 six.audio.voiceover_performed 必须逐字保留，不得改写、删减或替换措辞。必须在输出中包含【全段口播（逐字保留）】块，内容为 full_voiceover_verbatim 原文（若为英文则保持英文）。
2. **六要素硬保留**：每个 sub_shot 的 six 中主体、运动、环境、运镜/切镜、美学须在输出中有对应「主体：」「运动：」「环境：」「运镜」「美学：」标签表达，不得删除或留空。
3. **发声硬保留**：每镜 six.audio.delivery_prompt 须在输出中以【发声】块保留（允许体验化改写措辞，但不得删除发声维度：声音/语速/停顿/尾音）。
4. **多镜头保结构**：按 sub_shots 的时间顺序呈现 2 至 6 个自然分段，保留 beat_role、emotion 与场景流转，不要压成一段散文。
5. **切镜硬保留**：每镜 six.camera_cut 中的 cut_type、transition_out（如硬切/叠化/闪白）及时间点不得删除或合并。
6. **弱化工业化语言**：删除或转译景别代号（MS/CU/FS）、焦段、机位参数、镜头编号；保留对情绪、叙事、观看感受有帮助的表达。
7. **禁止只写情绪名**：不得仅写「兴奋地说」「紧张地说」，须写出声音大小、语速、停顿、尾音变化。
8. **改写模式**：多镜头体验改写 + 叙事改写；强化故事与氛围，不凭空增加未给出的剧情。
9. **长度**：有完整口播时可超过 120 字；不要显著长于必要信息量。
10. **人物参考硬保留**：若输入 JSON 中 face_ref_index > 0，【视觉锚点】须保留人物参照说明，不得删除：
   - face_ref_mode 为 pencil（或未指定）时：须含「把图N还原成写实照片风格，超写实人像摄影」（N 为 face_ref_index）
   - face_ref_mode 为 seedream 时：须含「Seedream 合规生成」
11. **画外音模式**：若 voiceover_mode=off_screen，禁止在画面分镜中添加人物；口播仅出现在【全段口播】与【台词】；禁止口型描写
12. **无口播模式**：若 voiceover_mode=none 或 full_voiceover_verbatim 为空，禁止【全段口播】与【发声】块
13. **多图指代**：若输入 JSON 含 reference_roles 且多于 1 条产品/补充角色，【视觉锚点】须逐条声明「参考图N为…」；分镜「主体」须保留输入中的图号指代，不得全部改成参考图1；无脸多图时禁止凭空添加人物
14. **generic 虚拟人物保留**：若 requires_generic_person=true 且 presentation_mode=on_screen_hand，【视觉锚点】人物描述须保留手部出镜语义，禁止改为露脸博主或删除人物；禁止添加「人物面部由 AI 生成」类露脸约束
15. **generic 露脸保留**：若 requires_generic_person=true 且 presentation_mode 为 on_screen_face/on_screen_body，【视觉锚点】须保留人物描述与「勿复刻原视频特定人脸」约束，禁止 strip 人物

## 输出格式（仅输出一条纯文本 prompt，不要 Markdown 代码块，不要「判断/执行动作」等元说明）
【主题】…
【视觉锚点】…
【段内分镜 start-end s】每镜含：主体/运动/环境/运镜/美学/音频（【发声】+【台词】）
【全段口播（逐字保留）】「原文」
【背景音】…（如有）
【约束】R2V 写「严格跟随参考视频镜头切分与节奏，跟随段内切点，不要压成一镜到底」；I2V 写「按分镜时间顺序连贯呈现，每镜切换处执行对应切镜方式」；均禁止字幕水印。

禁止在 JSON 外输出任何解释。"""


def build_vc_refine_user_text(
    bundle_json: str,
    task_type: str,
    voiceover_language: str = "zh",
    voiceover_mode: str = "on_screen",
    requires_generic_person: bool = False,
    presentation_mode: str = "none",
) -> str:
    lang_note = ""
    if is_non_chinese_voiceover(voiceover_language):
        label = voiceover_language_label(voiceover_language)
        lang_note = (
            f"口播语言为 {label}：【全段口播】与【台词】须保留{label}原文；画面六要素标签仍用中文。\n"
        )
    mode_note = f"voiceover_mode={voiceover_mode}。"
    if voiceover_mode == "off_screen":
        mode_note += "画外音：画面无人物、无口型。"
    elif voiceover_mode == "none":
        mode_note += "无口播：禁止口播与发声块。"
    if requires_generic_person:
        mode_note += "requires_generic_person=true：保留输入人物锚点，禁止删除博主/手部模特描述。"
    if presentation_mode == "on_screen_hand":
        mode_note += "presentation_mode=on_screen_hand：仅手部出镜，禁止添加 AI 生成脸部约束。"
    return f"""请将以下 Seedance 段结构提纯为一条 VC 风格视频提示词（画面中文 + 口播保留原文语言）。
task_type={task_type}（r2v 需强调跟随参考视频切镜与段内切点；i2v 强调按时间顺序连贯分镜并执行切镜方式）。
{mode_note}
{lang_note}硬约束：full_voiceover_verbatim（performed 口播）必须原样出现在【全段口播（逐字保留）】中；六要素标签与【发声】块不可删除（无口播时除外）。

输入 JSON：
{bundle_json}
"""
