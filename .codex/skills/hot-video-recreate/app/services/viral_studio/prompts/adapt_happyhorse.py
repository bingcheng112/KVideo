"""Pass B：Happyhorse 脚本迁移 prompt（六要素 + reference_roles + 具体指代）。"""
from __future__ import annotations

from typing import Optional

from app.services.viral_studio.content_profile import ContentProfile
from app.services.viral_studio.prompts.adapt import ADAPT_SYSTEM, REWRITE_MODE_NOTE, build_adapt_user_text

def build_adapt_happyhorse_system(face_ref_index: int = 0) -> str:
    face_idx = max(0, int(face_ref_index or 0))
    char_rule = ""
    if face_idx > 0:
        char_rule = (
            f"- 产品固定「参考图1」；出镜人物固定「参考图{face_idx}」\n"
            f"- six.subject 须写「参考图{face_idx}中的{{人物}}」与「参考图1中的{{产品}}」等具体指代\n"
        )
    else:
        char_rule = "- 产品固定「参考图1」；six.subject 须写「参考图1中的{{具体产品}}」\n"

    extra_rules = f"""
18. **Happyhorse R2V 指代规范**：
{char_rule}- 每镜 audio.voiceover_semantic 控制在 1–2 句（利于口型同步）
19. 顶层必须输出 reference_roles 数组（1-based index 与参考图顺序一致）

输出 JSON 须在 global_consistency 同级增加 reference_roles，例如：
  "reference_roles": [{{"index": 1, "role": "product", "label": "产品名"}}{', {"index": ' + str(face_idx) + ', "role": "character", "label": "出镜人物"}' if face_idx > 0 else ''}]
"""

    json_patch = ADAPT_SYSTEM.replace(
        '  "reference_roles": [\n    {"index": 1, "role": "product", "label": "产品名称或外观"}\n  ]\n}',
        '  "reference_roles": [\n    {"index": 1, "role": "product", "label": "产品名称或外观"}\n  ]\n}',
    )
    return json_patch.replace(
        "禁止 Markdown 代码块；禁止在 JSON 外输出说明。",
        extra_rules + "\n禁止 Markdown 代码块；禁止在 JSON 外输出说明。",
    )


def build_adapt_happyhorse_user_text(
    product_name: str,
    product_info: str,
    dna_json: str,
    *,
    copy_mode: str = "preserve",
    genre: str = "",
    character_summary: str = "",
    face_reference_image_url: str = "",
    presented_gender: str = "",
    face_ref_index: int = 0,
    profile: Optional[ContentProfile] = None,
    forbidden_terms_hint: str = "",
) -> str:
    base = build_adapt_user_text(
        product_name,
        product_info,
        dna_json,
        copy_mode=copy_mode,
        genre=genre,
        character_summary=character_summary,
        face_reference_image_url=face_reference_image_url,
        presented_gender=presented_gender,
        profile=profile,
        forbidden_terms_hint=forbidden_terms_hint,
    )
    face_idx = max(0, int(face_ref_index or 0))
    if face_idx > 0:
        extra = (
            f"\n【Happyhorse】产品=参考图1，人物=参考图{face_idx}；"
            "输出 reference_roles 且 six.subject 含具体指代。"
        )
    else:
        extra = "\n【Happyhorse】产品=参考图1；输出 reference_roles。"
    return base + extra


__all__ = [
    "REWRITE_MODE_NOTE",
    "build_adapt_happyhorse_system",
    "build_adapt_happyhorse_user_text",
]
