"""viral-studio Chat 计费。"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from app.services.canvas_chat_billing import (
    estimate_chat_reserve_cost,
    estimate_omni_chat_reserve_cost,
    is_omni_plus,
    is_qwen35_plus,
    settle_chat_cost,
)


def estimate_omni_reserve_cost(
    messages_body: Dict[str, Any],
    model: str,
    *,
    video_seconds: int = 0,
    max_completion_tokens: int = 8192,
    text_only_output: bool = True,
) -> int:
    if is_omni_plus(model):
        return estimate_omni_chat_reserve_cost(
            messages_body,
            video_seconds=video_seconds,
            max_completion_tokens=max_completion_tokens,
            text_only_output=text_only_output,
        )
    if is_qwen35_plus(model):
        return estimate_chat_reserve_cost(
            messages_body,
            model,
            max_completion_tokens=max_completion_tokens,
        )
    from app.routers.canvas_proxy import calculate_cost

    return calculate_cost(model, "Chat")


async def settle_chat_cost_generic(
    user_id: str,
    reserved_cost: int,
    model: str,
    response_data: Any,
    db,
    *,
    video_seconds: int = 0,
    text_only_output: bool = True,
    text_prompt_tokens: int = 0,
) -> Tuple[int, int, int]:
    return await settle_chat_cost(
        user_id,
        reserved_cost,
        model,
        response_data,
        db,
        video_seconds=video_seconds,
        text_only_output=text_only_output,
        text_prompt_tokens=text_prompt_tokens,
    )
