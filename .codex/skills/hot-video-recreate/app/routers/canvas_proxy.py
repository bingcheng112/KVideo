"""独立包 stub：画布代理 / 密钥 / 算力（全部 no-op）。"""
from __future__ import annotations

import os
from typing import Any, Optional


def calculate_cost(model: str, api_type: str) -> int:
    return 0


async def try_reserve_credits(user_id: str, cost: int, db: Any) -> bool:
    return True


async def refund_reserved_credits(user_id: str, cost: int, db: Any) -> None:
    return None


async def log_canvas_consumption(
    user_id: str,
    cost: int,
    db: Any,
    model_name: str = "",
    api_type: str = "Chat",
    **kwargs: Any,
) -> None:
    return None


def _infer_canvas_base_url(base_url: Optional[str], match_pattern: str) -> str:
    return (base_url or "").strip().rstrip("/")


def _is_volc_ark_target(target_url: str) -> bool:
    low = (target_url or "").lower()
    return "ark.cn-beijing" in low or "volces.com" in low or "volcengine" in low


async def get_api_key_for_target(target_url: str) -> Optional[str]:
    """方舟目标用 VOLC_ARK_API_KEY，其余用 DASHSCOPE_API_KEY。"""
    if _is_volc_ark_target(target_url):
        key = (os.environ.get("VOLC_ARK_API_KEY") or "").strip()
        return key or None
    key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    return key or None
