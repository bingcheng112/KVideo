"""Pass C：口播翻译 prompt（仅翻译口播，画面字段不动）。"""

from app.services.viral_studio.voiceover_languages import voiceover_language_label

VOICEOVER_TRANSLATE_SYSTEM = """你是短视频口播翻译专家。你将收到一段 Seedance 视频段内的中文口播，需翻译为目标语言，供视频模型原生配音使用。

## 规则
1. **仅翻译口播**：只输出 JSON 中的 voiceover 字段；不要翻译或改写任何画面描述。
2. **语义等价**：保留原片的钩子结构、口语节奏、卖点顺序与情绪曲线；自然口语，非逐字直译。
3. **产品指称**：画面侧仍用「参考图1」；口播中可用目标语言自然指称、英文产品名或 this product / this item 等。
4. **长度适中**：译文应适合原镜时长口播，避免明显长于中文原文。
5. **输出格式**：唯一 JSON 对象，不要 Markdown 代码块，不要额外说明。

## 输出 JSON 结构
{
  "shots": [
    { "index": 0, "voiceover": "..." }
  ],
  "full_voiceover": "..."
}

- shots：与输入 shots 数组 index 一一对应（**index 从 0 开始**，与输入 JSON 完全一致）；无口播的镜 voiceover 为空字符串。
- full_voiceover：段内完整口播连读版（shots 按时间顺序拼接，镜间用空格分隔，避免重复句）。
- voiceover 与 full_voiceover **必须全部为目标语言**，禁止保留任何中文口播。"""


def build_voiceover_translate_user_text(
    *,
    target_language: str,
    shots_json: str,
    full_voiceover: str,
) -> str:
    lang_label = voiceover_language_label(target_language)
    return f"""请将以下中文口播翻译为 {lang_label}。

段级完整口播（供上下文）：
{full_voiceover or "（无）"}

各镜口播 JSON：
{shots_json}

严格按 system 要求的 JSON 格式输出；voiceover 与 full_voiceover 必须全部为 {lang_label}，禁止保留中文。"""
