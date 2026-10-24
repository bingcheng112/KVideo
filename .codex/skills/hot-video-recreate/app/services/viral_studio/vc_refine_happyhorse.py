"""Pass C 可选：Happyhorse Vibe Creating 提纯。"""
from __future__ import annotations

import json
import logging
from typing import List, Literal, Tuple

from app.services.viral_studio.config_resolver import pick_plus_config
from app.services.viral_studio.happyhorse_prompt import (
    build_happyhorse_prompt,
    happyhorse_structure_preserved,
)
from app.services.viral_studio.happyhorse_refs import to_happyhorse_image_refs
from app.services.viral_studio.omni_client import chat_completion_stream
from app.services.viral_studio.prompts.vc_refine_happyhorse import (
    VC_REFINE_HAPPYHORSE_SYSTEM,
    build_vc_refine_happyhorse_user_text,
)
from app.services.viral_studio.schemas import AdaptedScript
from app.services.viral_studio.segment_merge import SegmentBundle, voiceover_preserved_in_output

logger = logging.getLogger(__name__)

PromptSource = Literal["template", "vc", "vc_fallback"]


async def vc_refine_happyhorse_segment_prompt(
    user_id: str,
    bundle: SegmentBundle,
    *,
    adapted_script: AdaptedScript,
    reference_image_urls: List[str],
    face_ref_index: int = 0,
) -> Tuple[str, PromptSource, int]:
    """Happyhorse VC 提纯；失败回退 build_happyhorse_prompt。"""
    fallback = build_happyhorse_prompt(
        bundle,
        reference_image_urls=reference_image_urls,
        face_ref_index=face_ref_index,
        adapted_script=adapted_script,
    )
    verbatim = bundle.full_voiceover_verbatim

    try:
        _cfg, target_url, model_name = await pick_plus_config()
    except Exception as e:
        logger.warning("Happyhorse VC：模型配置不可用，回退模板: %s", e)
        return fallback, "vc_fallback", 0

    bundle_json = json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False)
    messages = [
        {"role": "system", "content": VC_REFINE_HAPPYHORSE_SYSTEM},
        {
            "role": "user",
            "content": build_vc_refine_happyhorse_user_text(
                bundle_json,
                voiceover_language=bundle.voiceover_language or "zh",
            ),
        },
    ]

    try:
        raw, _resp, cost, _bal = await chat_completion_stream(
            user_id,
            target_url=target_url,
            model_name=model_name,
            messages=messages,
            max_tokens=2048,
            video_seconds=0,
            consumption_remark="viral-studio-vc-refine-happyhorse",
        )
    except Exception as e:
        logger.warning("Happyhorse VC LLM 失败，回退模板: %s", e)
        return fallback, "vc_fallback", 0

    refined = (raw or "").strip()
    if refined.startswith("```"):
        refined = refined.split("\n", 1)[-1]
        if refined.endswith("```"):
            refined = refined.rsplit("```", 1)[0]
        refined = refined.strip()

    if not refined:
        return fallback, "vc_fallback", cost

    refined = to_happyhorse_image_refs(refined)

    if not voiceover_preserved_in_output(refined, verbatim):
        logger.warning(
            "Happyhorse VC 口播校验失败 segment=%s，回退模板",
            bundle.segment_index,
        )
        return fallback, "vc_fallback", cost

    if not happyhorse_structure_preserved(refined):
        logger.warning(
            "Happyhorse VC 结构校验失败 segment=%s，回退模板",
            bundle.segment_index,
        )
        return fallback, "vc_fallback", cost

    return refined, "vc", cost
