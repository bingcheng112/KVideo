"""Pass B：脚本迁移（B1 口播 + B2 分镜 orchestrator）。"""
from __future__ import annotations

import json
import logging
from typing import List, Tuple

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.url_safety import is_safe_http_url
from app.services.viral_studio.adapt_scene_fix import fix_failed_scenes
from app.services.viral_studio.config_resolver import pick_plus_config
from app.services.viral_studio.content_profile import ContentProfile, VoiceoverMode, build_content_profile
from app.services.viral_studio.content_sanitize import sanitize_adapted_script
from app.services.viral_studio.gender_align import (
    align_script_gender,
    detect_dna_gender,
    infer_target_gender,
    should_align_gender,
)
from app.services.viral_studio.json_utils import parse_json_object
from app.services.viral_studio.omni_client import chat_completion_stream
from app.services.viral_studio.presentation_inherit import apply_presentation_inherit
from app.services.viral_studio.presentation_profile import (
    extract_presentation_profile,
    presentation_has_person,
)
from app.services.viral_studio.product_profile import (
    collect_forbidden_terms,
    extract_source_product_profile,
)
from app.services.viral_studio.prompts.adapt import ADAPT_SYSTEM, build_adapt_user_text
from app.services.viral_studio.prompts.adapt_happyhorse import (
    build_adapt_happyhorse_system,
    build_adapt_happyhorse_user_text,
)
from app.services.viral_studio.reference_roles import infer_reference_roles
from app.services.viral_studio.schemas import AdaptedScript, UsageInfo, VideoDNA
from app.services.viral_studio.script_adapt_merge import (
    apply_voiceover_segments_to_script,
    empty_voiceover_segments,
    merge_b2_into_script,
)
from app.services.viral_studio.script_adapt_scenes import adapt_scenes
from app.services.viral_studio.script_adapt_voiceover import adapt_voiceover
from app.services.viral_studio.script_coherence import check_and_fix_script_coherence
from app.services.viral_studio.six_elements import build_scene_six, match_omni_entry
from app.services.viral_studio.voice_delivery import refine_voice_delivery

logger = logging.getLogger(__name__)

_USER_FRIENDLY_ADAPT_FAIL = "脚本迁移失败，请稍后重试"


def _validate_image_urls(urls: List[str]) -> List[str]:
    out: List[str] = []
    for u in urls or []:
        s = (u or "").strip()
        if not s:
            continue
        if not is_safe_http_url(s):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"reference_image_urls 须为公网 http(s) 地址: {s[:80]}",
            )
        out.append(s)
    return out


def _has_face_reference(
    *,
    character_summary: str = "",
    presented_gender: str = "",
    face_reference_image_url: str = "",
) -> bool:
    pg = (presented_gender or "").strip().lower()
    return bool(
        (face_reference_image_url or "").strip()
        or (character_summary or "").strip()
        or pg in ("female", "male")
    )


def _post_process_script(
    script: AdaptedScript,
    video_dna: VideoDNA,
    *,
    product_name: str = "",
    character_summary: str = "",
    presented_gender: str = "",
    face_ref_index: int = 0,
    reference_image_count: int = 0,
    profile: ContentProfile | None = None,
    source_profile=None,
    forbidden_terms: List[str] | None = None,
) -> AdaptedScript:
    """gender_align → merge_structure → coherence → presentation_inherit → voice_delivery → sanitize。"""
    script = apply_voiceover_segments_to_script(script)

    global_tone = (script.global_consistency.tone or "").strip()
    inferred = script.inferred_product

    if source_profile and not script.source_product:
        script.source_product = source_profile

    target_gender = infer_target_gender(character_summary, presented_gender)
    source_gender = detect_dna_gender(video_dna)
    do_gender_align = _has_face_reference(
        character_summary=character_summary,
        presented_gender=presented_gender,
    ) and should_align_gender(target_gender, source_gender)

    if do_gender_align:
        script = align_script_gender(script, target_gender)

    terms = forbidden_terms or []
    if source_profile and not terms:
        terms = collect_forbidden_terms(source_profile)

    for scene in script.adapted_script:
        omni = match_omni_entry(
            video_dna,
            float(scene.start_sec or 0),
            float(scene.end_sec or 0),
        )
        merged_six = build_scene_six(scene, omni, global_tone=global_tone)
        scene.six = merged_six
        if not scene.six.audio.voiceover_semantic and scene.new_voiceover:
            scene.six.audio.voiceover_semantic = scene.new_voiceover.strip()
        refine_voice_delivery(
            scene,
            environment=scene.six.environment,
            global_tone=global_tone,
            profile=profile,
        )
        scene.new_voiceover = scene.six.audio.voiceover_semantic or scene.new_voiceover
        if not scene.visual_brief and scene.six.environment:
            scene.visual_brief = scene.six.environment
        if not scene.camera and scene.six.camera_cut:
            scene.camera = scene.six.camera_cut

    if not script.reference_roles:
        product_label = (inferred.name if inferred else "") or product_name or "产品"
        script.reference_roles = infer_reference_roles(
            image_count=max(1, int(reference_image_count or 1)),
            face_ref_index=face_ref_index,
            product_label=product_label,
            character_label=(script.global_consistency.character or character_summary or "出镜人物"),
        )

    if source_profile:
        script, _report = check_and_fix_script_coherence(
            script,
            video_dna,
            source_profile,
            terms,
        )

    presentation = extract_presentation_profile(video_dna)
    if profile is not None and presentation_has_person(presentation):
        script = apply_presentation_inherit(
            script,
            video_dna,
            presentation,
            profile,
        )
    elif profile is not None:
        script.presentation_profile = presentation

    if source_profile or profile is not None:
        for scene in script.adapted_script or []:
            refine_voice_delivery(
                scene,
                environment=scene.six.environment if scene.six else "",
                global_tone=global_tone,
                profile=profile,
            )

    if profile is not None:
        script = sanitize_adapted_script(script, video_dna, profile)
    return script


async def _run_scene_fix_loop(
    user_id: str,
    *,
    target_url: str,
    model_name: str,
    script: AdaptedScript,
    video_dna: VideoDNA,
    forbidden_terms: List[str],
    profile: ContentProfile,
    source_profile,
    product_name: str,
    character_summary: str,
    presented_gender: str,
    face_ref_index: int,
    reference_image_count: int,
    visual_only: bool,
) -> Tuple[AdaptedScript, int]:
    cost = 0
    report = script.coherence_report
    already_retried: set[int] = set()
    max_iterations = int(getattr(settings, "VIRAL_SCENE_FIX_MAX_ITERATIONS", 5))
    iteration = 0

    while iteration < max_iterations:
        if not report or report.passed or not report.failed_scene_ids:
            break
        script, fix_cost, already_retried = await fix_failed_scenes(
            user_id,
            target_url=target_url,
            model_name=model_name,
            script=script,
            forbidden_terms=forbidden_terms,
            report=report,
            visual_only=visual_only,
            already_retried=already_retried,
        )
        cost += fix_cost
        if fix_cost == 0:
            break
        script = _post_process_script(
            script,
            video_dna,
            product_name=product_name,
            character_summary=character_summary,
            presented_gender=presented_gender,
            face_ref_index=face_ref_index,
            reference_image_count=reference_image_count,
            profile=profile,
            source_profile=source_profile,
            forbidden_terms=forbidden_terms,
        )
        report = script.coherence_report
        iteration += 1
    return script, cost


async def _adapt_script_split(
    user_id: str,
    *,
    video_dna: VideoDNA,
    product_name: str,
    product_info: str,
    reference_image_urls: List[str],
    copy_mode: str,
    character_summary: str,
    face_reference_image_url: str,
    presented_gender: str,
    target_engine: str,
    face_ref_index: int,
    profile: ContentProfile,
    source_profile,
    forbidden_terms: List[str],
    forbidden_hint: str,
    ref_count: int,
    presentation_json: str,
) -> Tuple[AdaptedScript, int, int]:
    """B1+B2 拆分迁移。返回 (script, cost, balance)。"""
    cost = 0
    segments = empty_voiceover_segments(video_dna)
    b1_partial = AdaptedScript(voiceover_segments=segments)
    balance = 0

    if profile.voiceover_mode != VoiceoverMode.NONE:
        b1_partial, b1_cost, balance = await adapt_voiceover(
            user_id,
            video_dna=video_dna,
            product_name=product_name,
            product_info=product_info,
            reference_image_urls=reference_image_urls,
            copy_mode=copy_mode,
            profile=profile,
            forbidden_terms_hint=forbidden_hint,
            target_engine=target_engine,
            face_reference_image_url=face_reference_image_url,
        )
        cost += b1_cost
        segments = b1_partial.voiceover_segments or segments

    b2_data, b2_cost, b2_bal = await adapt_scenes(
        user_id,
        video_dna=video_dna,
        b1_partial=b1_partial,
        voiceover_segments=segments,
        reference_image_urls=reference_image_urls,
        profile=profile,
        forbidden_terms_hint=forbidden_hint,
        target_engine=target_engine,
        face_ref_index=face_ref_index,
        character_summary=character_summary,
        face_reference_image_url=face_reference_image_url,
        presented_gender=presented_gender,
        presentation_json=presentation_json,
    )
    cost += b2_cost
    balance = b2_bal

    script = merge_b2_into_script(
        b1_partial=b1_partial,
        b2_data=b2_data,
        video_dna=video_dna,
    )
    return script, cost, balance


async def _adapt_script_legacy(
    user_id: str,
    *,
    video_dna: VideoDNA,
    product_name: str,
    product_info: str,
    reference_image_urls: List[str],
    copy_mode: str,
    character_summary: str,
    face_reference_image_url: str,
    presented_gender: str,
    target_engine: str,
    face_ref_index: int,
    profile: ContentProfile,
    source_profile,
    forbidden_terms: List[str],
    forbidden_hint: str,
    ref_count: int,
    presentation_json: str,
) -> Tuple[AdaptedScript, dict, int, int]:
    """旧版单次 plus 迁移（VIRAL_ADAPT_LEGACY=true 回退）。"""
    _cfg, target_url, model_name = await pick_plus_config()
    dna_json = json.dumps(video_dna.model_dump(), ensure_ascii=False)
    genre = (video_dna.meta.genre or "").strip()
    engine = (target_engine or "seedance").strip().lower()
    imgs = reference_image_urls
    face_url = face_reference_image_url

    if engine == "happyhorse":
        system_content = build_adapt_happyhorse_system(face_ref_index=face_ref_index)
        user_text = build_adapt_happyhorse_user_text(
            product_name,
            product_info,
            dna_json,
            copy_mode=copy_mode,
            genre=genre,
            character_summary=character_summary,
            face_reference_image_url=face_url,
            presented_gender=presented_gender,
            face_ref_index=face_ref_index,
            profile=profile,
            forbidden_terms_hint=forbidden_hint,
        )
    else:
        system_content = ADAPT_SYSTEM
        user_text = build_adapt_user_text(
            product_name,
            product_info,
            dna_json,
            copy_mode=copy_mode,
            genre=genre,
            character_summary=character_summary,
            face_reference_image_url=face_url,
            presented_gender=presented_gender,
            profile=profile,
            product_image_count=len(imgs),
            forbidden_terms_hint=forbidden_hint,
            presentation_json=presentation_json,
        )

    content_parts: List[dict] = []
    for url in imgs[:8]:
        content_parts.append({"type": "image_url", "image_url": {"url": url}})
    if face_url:
        content_parts.append({"type": "image_url", "image_url": {"url": face_url}})
    content_parts.append({"type": "text", "text": user_text})

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": content_parts},
    ]

    raw, resp_data, cost, balance = await chat_completion_stream(
        user_id,
        target_url=target_url,
        model_name=model_name,
        messages=messages,
        max_tokens=6144,
        video_seconds=0,
        consumption_remark="viral-studio-adapt",
    )

    data = parse_json_object(raw)
    script = AdaptedScript.from_dict(data)
    return script, resp_data, cost, balance


async def adapt_script(
    user_id: str,
    *,
    video_dna: VideoDNA,
    product_name: str = "",
    product_info: str = "",
    reference_image_urls: List[str],
    copy_mode: str = "preserve",
    character_summary: str = "",
    face_reference_image_url: str = "",
    presented_gender: str = "",
    target_engine: str = "seedance",
    face_ref_index: int = 0,
) -> Tuple[AdaptedScript, UsageInfo, int, int]:
    imgs = _validate_image_urls(reference_image_urls)
    if not imgs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="至少需要 1 张产品参考图",
        )

    face_url = (face_reference_image_url or "").strip()
    if face_url and not is_safe_http_url(face_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="face_reference_image_url 须为公网 http(s) 地址",
        )

    source_profile = extract_source_product_profile(video_dna)
    forbidden_terms = collect_forbidden_terms(source_profile)
    forbidden_hint = "、".join(forbidden_terms[:15]) if forbidden_terms else ""
    presentation = extract_presentation_profile(video_dna)
    presentation_json = json.dumps(presentation.model_dump(), ensure_ascii=False)

    _cfg, target_url, model_name = await pick_plus_config()
    ref_count = len(imgs) + (1 if face_url else 0)
    profile = build_content_profile(
        video_dna,
        face_ref_index=face_ref_index,
        character_summary=character_summary,
        presented_gender=presented_gender,
        presentation=presentation,
    )

    use_legacy = bool(getattr(settings, "VIRAL_ADAPT_LEGACY", False))
    cost = 0
    resp_data: dict = {}
    balance = 0

    try:
        if use_legacy:
            script, resp_data, adapt_cost, balance = await _adapt_script_legacy(
                user_id,
                video_dna=video_dna,
                product_name=product_name,
                product_info=product_info,
                reference_image_urls=imgs,
                copy_mode=copy_mode,
                character_summary=character_summary,
                face_reference_image_url=face_url,
                presented_gender=presented_gender,
                target_engine=target_engine,
                face_ref_index=face_ref_index,
                profile=profile,
                source_profile=source_profile,
                forbidden_terms=forbidden_terms,
                forbidden_hint=forbidden_hint,
                ref_count=ref_count,
                presentation_json=presentation_json,
            )
            cost += adapt_cost
            visual_only = False
        else:
            script, adapt_cost, balance = await _adapt_script_split(
                user_id,
                video_dna=video_dna,
                product_name=product_name,
                product_info=product_info,
                reference_image_urls=imgs,
                copy_mode=copy_mode,
                character_summary=character_summary,
                face_reference_image_url=face_url,
                presented_gender=presented_gender,
                target_engine=target_engine,
                face_ref_index=face_ref_index,
                profile=profile,
                source_profile=source_profile,
                forbidden_terms=forbidden_terms,
                forbidden_hint=forbidden_hint,
                ref_count=ref_count,
                presentation_json=presentation_json,
            )
            cost += adapt_cost
            visual_only = True

        script = _post_process_script(
            script,
            video_dna,
            product_name=product_name,
            character_summary=character_summary,
            presented_gender=presented_gender,
            face_ref_index=face_ref_index,
            reference_image_count=ref_count,
            profile=profile,
            source_profile=source_profile,
            forbidden_terms=forbidden_terms,
        )

        fix_cost = 0
        script, fix_cost = await _run_scene_fix_loop(
            user_id,
            target_url=target_url,
            model_name=model_name,
            script=script,
            video_dna=video_dna,
            forbidden_terms=forbidden_terms,
            profile=profile,
            source_profile=source_profile,
            product_name=product_name,
            character_summary=character_summary,
            presented_gender=presented_gender,
            face_ref_index=face_ref_index,
            reference_image_count=ref_count,
            visual_only=visual_only,
        )
        cost += fix_cost

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Adapt script 失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_USER_FRIENDLY_ADAPT_FAIL,
        ) from e

    char_sum = (character_summary or "").strip()
    if (
        char_sum
        and not (script.global_consistency.character or "").strip()
        and (profile.has_on_screen_person or profile.has_face_ref)
    ):
        script.global_consistency.character = char_sum

    usage = resp_data.get("usage") or {}
    usage_info = UsageInfo(
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )
    return script, usage_info, cost, balance
