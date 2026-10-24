"""Pass C 可选：Vibe Creating 提纯。"""
from __future__ import annotations

import json
import logging
from typing import Literal, Tuple

from app.services.viral_studio.config_resolver import pick_plus_config
from app.services.viral_studio.omni_client import chat_completion_stream
from app.services.viral_studio.prompts.vc_refine import VC_REFINE_SYSTEM, build_vc_refine_user_text
from app.services.viral_studio.segment_merge import (
    SegmentBundle,
    build_deterministic_prompt,
    six_elements_preserved,
    voiceover_preserved_in_output,
)

logger = logging.getLogger(__name__)

PromptSource = Literal["template", "vc", "vc_fallback"]


async def vc_refine_segment_prompt(
    user_id: str,
    bundle: SegmentBundle,
) -> Tuple[str, PromptSource, int]:
    """
    尝试 VC 提纯。返回 (prompt, prompt_source, cost)。
    失败或口播校验不通过时回退 template。
    """
    fallback = build_deterministic_prompt(bundle)
    verbatim = bundle.full_voiceover_verbatim

    try:
        _cfg, target_url, model_name = await pick_plus_config()
    except Exception as e:
        logger.warning("VC 提纯：模型配置不可用，回退模板: %s", e)
        return fallback, "vc_fallback", 0

    bundle_json = json.dumps(
        bundle.model_dump(mode="json"),
        ensure_ascii=False,
    )
    messages = [
        {"role": "system", "content": VC_REFINE_SYSTEM},
        {
            "role": "user",
            "content": build_vc_refine_user_text(
                bundle_json,
                bundle.task_type,
                voiceover_language=bundle.voiceover_language or "zh",
                voiceover_mode=bundle.voiceover_mode or "on_screen",
                requires_generic_person=bool(bundle.requires_generic_person),
                presentation_mode=bundle.presentation_mode or "none",
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
            consumption_remark="viral-studio-vc-refine",
        )
    except Exception as e:
        logger.warning("VC 提纯 LLM 失败，回退模板: %s", e)
        return fallback, "vc_fallback", 0

    refined = (raw or "").strip()
    if refined.startswith("```"):
        refined = refined.split("\n", 1)[-1]
        if refined.endswith("```"):
            refined = refined.rsplit("```", 1)[0]
        refined = refined.strip()

    if not refined:
        return fallback, "vc_fallback", cost

    if not voiceover_preserved_in_output(refined, verbatim):
        logger.warning(
            "VC 提纯口播校验失败 segment=%s，回退模板",
            bundle.segment_index,
        )
        return fallback, "vc_fallback", cost

    if not six_elements_preserved(refined, bundle):
        logger.warning(
            "VC 提纯六要素校验失败 segment=%s，回退模板",
            bundle.segment_index,
        )
        return fallback, "vc_fallback", cost

    return refined, "vc", cost
