"""Pass C：Seedance 提示词编译。"""
from __future__ import annotations

import asyncio
from typing import List, Literal, Optional, Tuple

from app.services.viral_studio.content_profile import VoiceoverMode, build_content_profile
from app.services.viral_studio.person_detection import detect_real_person_involvement
from app.services.viral_studio.presentation_profile import extract_presentation_profile
from app.services.viral_studio.reference_roles import resolve_reference_roles
from app.services.viral_studio.schemas import (
    AdaptedScript,
    CompileResult,
    GlobalConsistency,
    PlannedSegment,
    SeedanceSegment,
    VideoDNA,
)
from app.services.viral_studio.script_compile_prepare import prepare_adapted_script_for_compile
from app.services.viral_studio.segment_merge import build_deterministic_prompt, build_segment_bundle
from app.services.viral_studio.segment_planner import plan_segments
from app.services.viral_studio.vc_refine import vc_refine_segment_prompt
from app.services.viral_studio.voiceover_translate import (
    VOICEOVER_LANGUAGE_ZH,
    normalize_voiceover_language,
    translate_voiceover_bundle,
)
from app.services.seedance_viral_routing import resolve_ark_model_async


def _pick_task_type(
    index: int,
    total: int,
    strategy: str,
    genre: str,
    *,
    voiceover_mode: VoiceoverMode = VoiceoverMode.ON_SCREEN,
) -> Literal["i2v", "r2v"]:
    s = (strategy or "i2v").strip().lower()
    if s == "i2v":
        return "i2v"
    if s == "r2v":
        return "r2v"
    if index == 0 and voiceover_mode == VoiceoverMode.ON_SCREEN and "口播" in genre:
        return "i2v"
    if index == 0:
        return "i2v"
    return "r2v"


async def _resolve_prompt_for_bundle(
    user_id: str,
    bundle,
    *,
    use_vc_refine: bool,
) -> Tuple[str, str, int]:
    """返回 (prompt, prompt_source, cost)。"""
    if use_vc_refine:
        prompt, source, cost = await vc_refine_segment_prompt(user_id, bundle)
        return prompt, source, cost
    template = build_deterministic_prompt(bundle)
    return template, "template", 0


async def compile_seedance_segments(
    user_id: str,
    *,
    video_dna: VideoDNA,
    adapted_script: AdaptedScript,
    reference_video_url: str,
    reference_image_urls: List[str],
    compile_strategy: str = "i2v",
    max_segment_sec: float = 15.0,
    split_reference_video: bool = False,
    use_vc_refine: bool = False,
    face_ref_index: int = 0,
    face_ref_mode: str = "pencil",
    voiceover_language: str = "zh",
    user_resolution: str = "720P",
) -> Tuple[CompileResult, int]:
    planned = plan_segments(video_dna, max_segment_sec=max_segment_sec)
    genre = video_dna.meta.genre or ""
    imgs = list(reference_image_urls or [])[:8]
    total = len(planned)
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
    reference_roles = resolve_reference_roles(
        adapted_script,
        reference_image_urls=imgs,
        face_ref_index=face_ref_index,
    )

    async def _build_one(i: int, plan: PlannedSegment) -> Tuple[SeedanceSegment, int]:
        raw_task_type = _pick_task_type(
            i,
            total,
            compile_strategy,
            genre,
            voiceover_mode=profile.voiceover_mode,
        )
        # 爆款复刻生成走全能参考（text + reference_image）；原片仅在 Pass A 拆解，不再作为 Ark reference_video
        task_type: Literal["i2v", "r2v"] = (
            raw_task_type if split_reference_video else "i2v"
        )
        bundle = build_segment_bundle(
            segment_index=i,
            start_sec=plan.start_sec,
            end_sec=plan.end_sec,
            duration=plan.duration,
            task_type=task_type,
            video_dna=video_dna,
            adapted_script=adapted_script,
            face_ref_index=face_ref_index,
            face_ref_mode=face_ref_mode,
            profile=profile,
            reference_roles=reference_roles,
        )
        lang = normalize_voiceover_language(voiceover_language)
        translate_cost = 0
        if lang != VOICEOVER_LANGUAGE_ZH:
            bundle, translate_cost = await translate_voiceover_bundle(
                user_id, bundle, lang
            )
            bundle.voiceover_language = lang
        prompt, prompt_source, vc_cost = await _resolve_prompt_for_bundle(
            user_id,
            bundle,
            use_vc_refine=effective_vc,
        )
        cost = translate_cost + vc_cost

        ref_video_url = None
        if split_reference_video and task_type == "r2v" and reference_video_url:
            from app.services.viral_studio.video_segment_split import split_and_upload_segment

            ref_video_url = await split_and_upload_segment(
                user_id,
                video_url=reference_video_url,
                start_sec=plan.start_sec,
                end_sec=plan.end_sec,
                max_segment_sec=max_segment_sec,
            )

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
            task_type=task_type,
            reference_video_url=ref_video_url,
            reference_image_urls=imgs,
            prompt=prompt,
            voiceover=bundle.full_voiceover_verbatim,
            audio_hint=bundle.audio_hints,
            continuity_from_prev=bundle.continuity_from_prev,
            transition_out=transition_out,
            prompt_source=prompt_source,
        )
        return seg, cost

    built = await asyncio.gather(*[_build_one(i, plan) for i, plan in enumerate(planned)])
    segments = [b[0] for b in built]
    total_vc_cost = sum(b[1] for b in built)
    segments.sort(key=lambda s: s.index)

    duration = float(video_dna.meta.duration_sec or 0)
    if not duration and planned:
        duration = planned[-1].end_sec

    face_url = ""
    if face_ref_index > 0 and face_ref_index <= len(imgs):
        face_url = imgs[face_ref_index - 1]

    involves, reason = detect_real_person_involvement(
        face_ref_index=face_ref_index,
        face_reference_image_url=face_url,
        video_dna=video_dna,
        adapted_script=adapted_script,
        segment_prompts=[s.prompt for s in segments],
        content_profile=profile,
    )
    has_face = face_ref_index > 0
    inferred = adapted_script.inferred_product
    text_heavy = bool(inferred.product_text_heavy) if inferred else False
    text_reason = (inferred.product_text_heavy_reason if inferred else "") or ""
    resolved_model = await resolve_ark_model_async(
        involves,
        has_face,
        user_resolution=user_resolution,
        product_text_heavy=text_heavy,
    )

    result = CompileResult(
        total_duration_sec=duration,
        segment_count=len(segments),
        segments=segments,
        global_consistency=adapted_script.global_consistency,
        voiceover_language=normalize_voiceover_language(voiceover_language),
        involves_real_person=involves,
        person_detection_reason=reason,
        resolved_ark_model=resolved_model,
        product_text_heavy=text_heavy,
        product_text_heavy_reason=text_reason,
    )
    return result, total_vc_cost
