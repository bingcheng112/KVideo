"""独立包 stub：Chat 计费（不扣费，估算恒为 0）。"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def is_qwen35_plus(model: str) -> bool:
    m = (model or "").strip().lower()
    return "qwen3.5-plus" in m and "omni" not in m


def is_omni_plus(model: str) -> bool:
    m = (model or "").strip().lower()
    return "omni-plus" in m or "qwen3.5-omni-plus" in m


def estimate_prompt_tokens_from_messages(body: Optional[Dict[str, Any]]) -> int:
    return 0


def estimate_omni_chat_reserve_cost(
    messages_body: Dict[str, Any],
    *,
    video_seconds: int = 0,
    max_completion_tokens: int = 8192,
    text_only_output: bool = True,
) -> int:
    return 0


def estimate_chat_reserve_cost(
    messages_body: Dict[str, Any],
    model: str,
    *,
    max_completion_tokens: int = 8192,
) -> int:
    return 0


async def settle_chat_cost(
    user_id: str,
    reserved_cost: int,
    model: str,
    response_data: Any,
    db: Any,
    *,
    video_seconds: int = 0,
    text_only_output: bool = True,
    text_prompt_tokens: int = 0,
) -> Tuple[int, int, int]:
    usage = {}
    if isinstance(response_data, dict):
        usage = response_data.get("usage") or {}
    pt = int(usage.get("prompt_tokens") or text_prompt_tokens or 0)
    ct = int(usage.get("completion_tokens") or 0)
    return 0, pt, ct
