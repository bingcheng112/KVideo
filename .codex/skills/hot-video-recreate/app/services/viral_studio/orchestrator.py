"""全流程编排。"""
from __future__ import annotations

from typing import List

from app.core.database import db
from app.services.viral_studio.omni_deconstruct import deconstruct_video
from app.services.viral_studio.schemas import (
    AdaptedScript,
    PipelineResult,
    UsageInfo,
    VideoDNA,
)
from app.services.viral_studio.script_adapt import adapt_script
from app.services.viral_studio.happyhorse_compile import compile_happyhorse_segments
from app.services.viral_studio.seedance_compile import compile_seedance_segments


async def run_full_pipeline(
    user_id: str,
    *,
    reference_video_url: str,
    reference_video_seconds: int,
    product_name: str = "",
    product_info: str = "",
    reference_image_urls: List[str],
    copy_mode: str = "preserve",
    character_summary: str = "",
    face_ref_index: int = 0,
    face_ref_mode: str = "pencil",
    presented_gender: str = "",
    compile_strategy: str = "i2v",
    max_segment_sec: float = 15.0,
    use_vc_refine: bool = False,
    voiceover_language: str = "zh",
    user_resolution: str = "720P",
) -> PipelineResult:
    dna, u1, c1, _bal1 = await deconstruct_video(
        user_id,
        reference_video_url=reference_video_url,
        reference_video_seconds=reference_video_seconds,
    )
    adapt_urls = list(reference_image_urls or [])
    face_url = ""
    if face_ref_index > 0 and face_ref_index <= len(adapt_urls):
        face_url = adapt_urls[face_ref_index - 1]
        adapt_urls = adapt_urls[: face_ref_index - 1]
    script, u2, c2, _bal2 = await adapt_script(
        user_id,
        video_dna=dna,
        product_name=product_name,
        product_info=product_info,
        reference_image_urls=adapt_urls,
        copy_mode=copy_mode,
        character_summary=character_summary,
        face_reference_image_url=face_url,
        presented_gender=presented_gender,
    )
    compile_result, vc_cost = await compile_seedance_segments(
        user_id,
        video_dna=dna,
        adapted_script=script,
        reference_video_url=reference_video_url,
        reference_image_urls=reference_image_urls,
        compile_strategy=compile_strategy,
        max_segment_sec=max_segment_sec,
        use_vc_refine=use_vc_refine,
        face_ref_index=face_ref_index,
        face_ref_mode=face_ref_mode,
        voiceover_language=voiceover_language,
        user_resolution=user_resolution,
    )

    total_cost = c1 + c2 + vc_cost

    row = await db.execute_one("SELECT credits FROM users WHERE id = %s", (user_id,))
    balance = int(row.get("credits") or 0) if row else 0

    usage = UsageInfo(
        prompt_tokens=u1.prompt_tokens + u2.prompt_tokens,
        completion_tokens=u1.completion_tokens + u2.completion_tokens,
    )

    return PipelineResult(
        video_dna=dna,
        adapted_script=script,
        compile_result=compile_result,
        usage=usage,
        cost=total_cost,
        remaining_balance=balance,
    )


async def run_happyhorse_pipeline(
    user_id: str,
    *,
    reference_video_url: str,
    reference_video_seconds: int,
    product_name: str = "",
    product_info: str = "",
    reference_image_urls: List[str],
    copy_mode: str = "preserve",
    character_summary: str = "",
    face_ref_index: int = 0,
    presented_gender: str = "",
    max_segment_sec: float = 15.0,
    use_vc_refine: bool = False,
    voiceover_language: str = "zh",
) -> PipelineResult:
    dna, u1, c1, _bal1 = await deconstruct_video(
        user_id,
        reference_video_url=reference_video_url,
        reference_video_seconds=reference_video_seconds,
    )
    adapt_urls = list(reference_image_urls or [])
    face_url = ""
    if face_ref_index > 0 and face_ref_index <= len(adapt_urls):
        face_url = adapt_urls[face_ref_index - 1]
        adapt_urls = adapt_urls[: face_ref_index - 1]
    script, u2, c2, _bal2 = await adapt_script(
        user_id,
        video_dna=dna,
        product_name=product_name,
        product_info=product_info,
        reference_image_urls=adapt_urls,
        copy_mode=copy_mode,
        character_summary=character_summary,
        face_reference_image_url=face_url,
        presented_gender=presented_gender,
        target_engine="happyhorse",
        face_ref_index=face_ref_index,
    )
    compile_result, vc_cost = await compile_happyhorse_segments(
        user_id,
        video_dna=dna,
        adapted_script=script,
        reference_image_urls=reference_image_urls,
        max_segment_sec=max_segment_sec,
        use_vc_refine=use_vc_refine,
        face_ref_index=face_ref_index,
        voiceover_language=voiceover_language,
    )

    total_cost = c1 + c2 + vc_cost

    row = await db.execute_one("SELECT credits FROM users WHERE id = %s", (user_id,))
    balance = int(row.get("credits") or 0) if row else 0

    usage = UsageInfo(
        prompt_tokens=u1.prompt_tokens + u2.prompt_tokens,
        completion_tokens=u1.completion_tokens + u2.completion_tokens,
    )

    return PipelineResult(
        video_dna=dna,
        adapted_script=script,
        compile_result=compile_result,
        usage=usage,
        cost=total_cost,
        remaining_balance=balance,
    )
