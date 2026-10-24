"""Pass B1：口播规划（adapt_voiceover）。"""
from __future__ import annotations

import json
import logging
from typing import List, Tuple

from fastapi import HTTPException, status

from app.services.viral_studio.config_resolver import pick_plus_config
from app.services.viral_studio.content_profile import ContentProfile
from app.services.viral_studio.json_utils import parse_json_object
from app.services.viral_studio.omni_client import chat_completion_stream
from app.services.viral_studio.prompts.adapt_voiceover import (
    ADAPT_VOICEOVER_SYSTEM,
    build_adapt_voiceover_user_text,
)
from app.services.viral_studio.schemas import AdaptedScript, BeatPlanEntry, VideoDNA, VoiceoverSegment
from app.services.viral_studio.script_adapt_merge import (
    align_voiceover_segments,
    find_duplicate_segment_scene_ids,
)

logger = logging.getLogger(__name__)

_USER_FRIENDLY_FAIL = "口播规划失败，请稍后重试"


def _parse_b1_payload(data: dict) -> AdaptedScript:
    segments: List[VoiceoverSegment] = []
    for item in data.get("voiceover_segments") or []:
        if isinstance(item, dict):
            segments.append(VoiceoverSegment.model_validate(item))

    beat_plan: List[BeatPlanEntry] = []
    for item in data.get("beat_plan") or []:
        if isinstance(item, dict):
            beat_plan.append(BeatPlanEntry.model_validate(item))

    from app.services.viral_studio.schemas import InferredProduct, SourceProductProfile

    inferred = None
    if isinstance(data.get("inferred_product"), dict):
        inferred = InferredProduct.model_validate(data["inferred_product"])
    source = None
    if isinstance(data.get("source_product"), dict):
        source = SourceProductProfile.model_validate(data["source_product"])

    return AdaptedScript(
        inferred_product=inferred,
        source_product=source,
        full_voiceover=str(data.get("full_voiceover") or "").strip(),
        voiceover_segments=segments,
        beat_plan=beat_plan,
    )


async def adapt_voiceover(
    user_id: str,
    *,
    video_dna: VideoDNA,
    product_name: str = "",
    product_info: str = "",
    reference_image_urls: List[str],
    copy_mode: str = "preserve",
    profile: ContentProfile,
    forbidden_terms_hint: str = "",
    target_engine: str = "seedance",
    face_reference_image_url: str = "",
) -> Tuple[AdaptedScript, int, int]:
    """B1：生成 full_voiceover + voiceover_segments + beat_plan。返回 (script, cost, balance)。"""
    _cfg, target_url, model_name = await pick_plus_config()
    dna_json = json.dumps(video_dna.model_dump(), ensure_ascii=False)
    genre = (video_dna.meta.genre or "").strip()

    user_text = build_adapt_voiceover_user_text(
        product_name,
        product_info,
        dna_json,
        copy_mode=copy_mode,
        genre=genre,
        profile=profile,
        product_image_count=len(reference_image_urls),
        forbidden_terms_hint=forbidden_terms_hint,
        target_engine=target_engine,
    )

    content_parts: List[dict] = []
    for url in reference_image_urls[:8]:
        content_parts.append({"type": "image_url", "image_url": {"url": url}})
    face_url = (face_reference_image_url or "").strip()
    if face_url:
        content_parts.append({"type": "image_url", "image_url": {"url": face_url}})
    content_parts.append({"type": "text", "text": user_text})

    messages = [
        {"role": "system", "content": ADAPT_VOICEOVER_SYSTEM},
        {"role": "user", "content": content_parts},
    ]

    total_cost = 0
    script: AdaptedScript | None = None
    balance = 0

    for attempt in range(2):
        raw, _resp, cost, bal = await chat_completion_stream(
            user_id,
            target_url=target_url,
            model_name=model_name,
            messages=messages,
            max_tokens=4096,
            video_seconds=0,
            consumption_remark="viral-studio-adapt-voiceover",
        )
        total_cost += cost
        balance = bal
        try:
            data = parse_json_object(raw)
            script = _parse_b1_payload(data)
            script.voiceover_segments = align_voiceover_segments(
                script.voiceover_segments,
                video_dna,
                script.beat_plan,
            )
            dups = find_duplicate_segment_scene_ids(script.voiceover_segments)
            if dups and attempt == 0:
                logger.warning("B1 口播重复 scene_ids=%s，重试一次", dups)
                messages.append({"role": "assistant", "content": raw})
                messages.append(
                    {
                        "role": "user",
                        "content": f"voiceover_segments 存在重复口播（scene_id={dups}），请重写重复镜的 text，保证全片 normalize 后无完全相同句子。",
                    }
                )
                continue
            break
        except Exception as e:
            logger.warning("B1 JSON 解析失败 attempt=%s: %s raw=%s", attempt, e, raw[:1500])
            if attempt == 1:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=_USER_FRIENDLY_FAIL,
                ) from e

    if script is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_USER_FRIENDLY_FAIL,
        )
    return script, total_cost, balance
