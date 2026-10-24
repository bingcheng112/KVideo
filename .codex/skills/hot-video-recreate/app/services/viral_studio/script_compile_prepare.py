"""Pass C 编译前脚本兜底：呈现 inherit + 全片语气解析。"""
from __future__ import annotations

from app.services.viral_studio.content_profile import (
    build_content_profile,
    is_placeholder_text,
    resolve_global_tone,
)
from app.services.viral_studio.presentation_inherit import apply_presentation_inherit
from app.services.viral_studio.source_term_sanitize import apply_cross_category_to_script
from app.services.viral_studio.presentation_profile import (
    extract_presentation_profile,
    presentation_has_person,
)
from app.services.viral_studio.schemas import AdaptedScript, VideoDNA


def prepare_adapted_script_for_compile(
    script: AdaptedScript,
    video_dna: VideoDNA,
    *,
    face_ref_index: int = 0,
) -> AdaptedScript:
    """compile 入口兜底：inherit 清洗 + tone 占位符回填（无 LLM）。"""
    presentation = script.presentation_profile or extract_presentation_profile(video_dna)
    script.presentation_profile = presentation
    profile = build_content_profile(
        video_dna,
        face_ref_index=face_ref_index,
        presentation=presentation,
    )

    if presentation_has_person(presentation):
        script = apply_presentation_inherit(
            script,
            video_dna,
            presentation,
            profile,
        )

    script = apply_cross_category_to_script(script)

    resolved_tone = resolve_global_tone(script, video_dna)
    gc = script.global_consistency
    current = (gc.tone or "").strip()
    if not current or is_placeholder_text(current):
        gc = gc.model_copy(update={"tone": resolved_tone})
        script.global_consistency = gc

    return script
