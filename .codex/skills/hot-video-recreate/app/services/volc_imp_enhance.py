"""独立包 stub：跳过 MediaKit 超分，直接返回 Ark 原片。"""
from __future__ import annotations

from typing import Tuple


async def enhance_video_standard(
    video_url: str,
    target: str = "1080p",
) -> Tuple[str, str]:
    """返回 (enhance_task_id, video_url)。本包不做超分。"""
    _ = target
    return "", (video_url or "").strip()
