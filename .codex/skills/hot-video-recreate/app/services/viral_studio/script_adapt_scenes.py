"""Pass B2：分镜画面（adapt_scenes，口播锁定）。"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from fastapi import HTTPException, status

from app.services.viral_studio.config_resolver import pick_plus_config
from app.services.viral_studio.content_profile import ContentProfile
from app.services.viral_studio.json_utils import parse_json_object
from app.services.viral_studio.omni_client import chat_completion_stream
from app.services.viral_studio.prompts.adapt_scenes import (
    ADAPT_SCENES_SYSTEM,
    build_adapt_scenes_user_text,
)
from app.services.viral_studio.prompts.adapt_scenes_happyhorse import (
    build_adapt_scenes_happyhorse_system,
)
from app.services.viral_studio.schemas import AdaptedScript, VideoDNA, VoiceoverSegment

logger = logging.getLogger(__name__)

_USER_FRIENDLY_FAIL = "分镜生成失败，请稍后重试"


async def adapt_scenes(
    user_id: str,
    *,
    video_dna: VideoDNA,
    b1_partial: AdaptedScript,
    voiceover_segments: List[VoiceoverSegment],
    reference_image_urls: List[str],
    profile: ContentProfile,
    forbidden_terms_hint: str = "",
    target_engine: str = "seedance",
    face_ref_index: int = 0,
    character_summary: str = "",
    face_reference_image_url: str = "",
    presented_gender: str = "",
    presentation_json: str = "",
) -> Tuple[Dict[str, Any], int, int]:
    """B2：生成画面 adapted_script（不含口播）。返回 (data, cost, balance)。"""
    _cfg, target_url, model_name = await pick_plus_config()
    dna_json = json.dumps(video_dna.model_dump(), ensure_ascii=False)
    beat_json = json.dumps(
        [b.model_dump() for b in (b1_partial.beat_plan or [])],
        ensure_ascii=False,
    )
    inferred_json = json.dumps(
        b1_partial.inferred_product.model_dump() if b1_partial.inferred_product else {},
        ensure_ascii=False,
    )

    from app.services.viral_studio.presentation_profile import extract_presentation_profile

    presentation = extract_presentation_profile(video_dna)

    user_text = build_adapt_scenes_user_text(
        dna_json,
        voiceover_segments,
        beat_json,
        inferred_json,
        profile=profile,
        presentation=presentation,
        presentation_json=presentation_json,
        character_summary=character_summary,
        face_reference_image_url=face_reference_image_url,
        presented_gender=presented_gender,
        product_image_count=len(reference_image_urls),
        forbidden_terms_hint=forbidden_terms_hint,
    )

    engine = (target_engine or "seedance").strip().lower()
    if engine == "happyhorse":
        system_content = build_adapt_scenes_happyhorse_system(face_ref_index=face_ref_index)
    else:
        system_content = ADAPT_SCENES_SYSTEM

    content_parts: List[dict] = []
    for url in reference_image_urls[:8]:
        content_parts.append({"type": "image_url", "image_url": {"url": url}})
    face_url = (face_reference_image_url or "").strip()
    if face_url:
        content_parts.append({"type": "image_url", "image_url": {"url": face_url}})
    content_parts.append({"type": "text", "text": user_text})

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": content_parts},
    ]

    raw, _resp, cost, balance = await chat_completion_stream(
        user_id,
        target_url=target_url,
        model_name=model_name,
        messages=messages,
        max_tokens=6144,
        video_seconds=0,
        consumption_remark="viral-studio-adapt-scenes",
    )

    try:
        data = parse_json_object(raw)
    except Exception as e:
        logger.warning("B2 JSON 解析失败: %s raw=%s", e, raw[:2000])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_USER_FRIENDLY_FAIL,
        ) from e

    if not isinstance(data.get("adapted_script"), list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_USER_FRIENDLY_FAIL,
        )
    return data, cost, balance
