"""Pass C：Happyhorse 提示词编译（独立四段式，不依赖 Seedance 模板）。"""
from __future__ import annotations

import asyncio
from typing import List, Tuple

from app.services.viral_studio.content_profile import VoiceoverMode, build_content_profile
from app.services.viral_studio.happyhorse_prompt import build_happyhorse_prompt
from app.services.viral_studio.presentation_profile import extract_presentation_profile
from app.services.viral_studio.schemas import AdaptedScript, CompileResult, PlannedSegment, SeedanceSegment, VideoDNA
from app.services.viral_studio.script_compile_prepare import prepare_adapted_script_for_compile
from app.services.viral_studio.segment_merge import build_segment_bundle
from app.services.viral_studio.segment_planner import plan_segments
from app.services.viral_studio.vc_refine_happyhorse import vc_refine_happyhorse_segment_prompt
from app.services.viral_studio.voiceover_translate import (
    VOICEOVER_LANGUAGE_ZH,
    normalize_voiceover_language,
    translate_voiceover_bundle,
)


async def compile_happyhorse_segments(
    user_id: str,
    *,
    video_dna: VideoDNA,
    adapted_script: AdaptedScript,
    reference_image_urls: List[str],
    max_segment_sec: float = 15.0,
    use_vc_refine: bool = False,
    face_ref_index: int = 0,
    voiceover_language: str = "zh",
) -> Tuple[CompileResult, int]:
    """Happyhorse R2V：切段 + 四段式 prompt，仅 reference_image。"""
    planned = plan_segments(video_dna, max_segment_sec=max_segment_sec)
    imgs = list(reference_image_urls or [])[:9]
    lang = normalize_voiceover_language(voiceover_language)
    adapted_script = prepare_adapted_script_for_compile(
        adapted_script,
        video_dna,
        face_ref_index=face_ref_index,
    )
    presentation = adapted_script.presentation_profile or extract_presentation_profile(video_dna)
    profile = build_content_profile(
        video_dna,
        face_ref_index=face_ref_index,
        presentation=presentation,
    )
    effective_vc = use_vc_refine and profile.voiceover_mode != VoiceoverMode.NONE

    async def _build_one(i: int, plan: PlannedSegment) -> Tuple[SeedanceSegment, int]:
        bundle = build_segment_bundle(
            segment_index=i,
            start_sec=plan.start_sec,
            end_sec=plan.end_sec,
            duration=plan.duration,
            task_type="i2v",
            video_dna=video_dna,
            adapted_script=adapted_script,
            face_ref_index=face_ref_index,
            face_ref_mode="pencil",
            profile=profile,
        )
        translate_cost = 0
        if lang != VOICEOVER_LANGUAGE_ZH:
            bundle, translate_cost = await translate_voiceover_bundle(user_id, bundle, lang)
            bundle.voiceover_language = lang

        if effective_vc:
            prompt, prompt_source, vc_cost = await vc_refine_happyhorse_segment_prompt(
                user_id,
                bundle,
                adapted_script=adapted_script,
                reference_image_urls=imgs,
                face_ref_index=face_ref_index,
            )
        else:
            prompt = build_happyhorse_prompt(
                bundle,
                reference_image_urls=imgs,
                face_ref_index=face_ref_index,
                adapted_script=adapted_script,
            )
            prompt_source = "template"
            vc_cost = 0

        transition_out = ""
        for tr in video_dna.transitions:
            if abs(float(tr.at_sec) - plan.end_sec) < 0.5:
                transition_out = tr.type or "硬切"
                break

        seg = SeedanceSegment(
            index=i,
            start_sec=plan.start_sec,
            end_sec=plan.end_sec,
            duration=plan.duration,
            task_type="r2v",
            reference_video_url=None,
            reference_image_urls=imgs,
            prompt=prompt,
            voiceover=bundle.full_voiceover_verbatim,
            audio_hint=bundle.audio_hints,
            continuity_from_prev=bundle.continuity_from_prev,
            transition_out=transition_out,
            prompt_source=prompt_source,
        )
        return seg, translate_cost + vc_cost

    built = await asyncio.gather(*[_build_one(i, plan) for i, plan in enumerate(planned)])
    segments = [b[0] for b in built]
    total_cost = sum(b[1] for b in built)
    segments.sort(key=lambda s: s.index)

    duration = float(video_dna.meta.duration_sec or 0)
    if not duration and planned:
        duration = planned[-1].end_sec

    result = CompileResult(
        total_duration_sec=duration,
        segment_count=len(segments),
        segments=segments,
        global_consistency=adapted_script.global_consistency,
        voiceover_language=lang,
    )
    return result, total_cost
