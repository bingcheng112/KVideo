"""Pass B2 Happyhorse：分镜画面 prompt（R2V 指代 + 口播锁定）。"""
from __future__ import annotations

from app.services.viral_studio.prompts.adapt_scenes import ADAPT_SCENES_SYSTEM


def build_adapt_scenes_happyhorse_system(face_ref_index: int = 0) -> str:
    face_idx = max(0, int(face_ref_index or 0))
    if face_idx > 0:
        char_rule = (
            f"- 产品固定「参考图1」；出镜人物固定「参考图{face_idx}」\n"
            f"- six.subject 须写「参考图{face_idx}中的{{人物}}」与「参考图1中的{{产品}}」\n"
        )
    else:
        char_rule = "- 产品固定「参考图1」；six.subject 须写「参考图1中的{{具体产品}}」\n"

    extra = f"""
【Happyhorse R2V 指代规范】
{char_rule}- 口播已由 B1 锁定（1–2 句/镜），画面禁止改写口播
- reference_roles 须 1-based 与参考图顺序一致
"""
    return ADAPT_SCENES_SYSTEM.replace(
        "禁止 Markdown；禁止输出说明。",
        extra + "\n禁止 Markdown；禁止输出说明。",
    )
