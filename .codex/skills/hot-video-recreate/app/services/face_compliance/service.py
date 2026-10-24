"""人脸合规编排（独立包）。
默认 pencil：Seedream I2I 铅笔彩铅风格化。
"""
from __future__ import annotations

from typing import List, Tuple

from fastapi import HTTPException, status

from app.core.url_safety import is_safe_http_url
from app.services.face_compliance.pencil_style_i2i import style_transfer_face_pencil
from app.services.face_compliance.prompt_templates import (
    FaceComplianceMode,
    PENCIL_STYLE_TRANSFER_PROMPT,
)


async def _run_pencil_compliance(
    url: str,
    *,
    size: str,
) -> Tuple[str, List[str]]:
    candidate_urls = await style_transfer_face_pencil(url, size=size)
    return PENCIL_STYLE_TRANSFER_PROMPT, candidate_urls


async def run_face_compliance(
    api_key: str,
    source_image_url: str,
    *,
    mode: FaceComplianceMode = "pencil",
    n: int = 4,
    size: str = "4K",
) -> Tuple[str, List[str]]:
    """
    人脸合规。默认 pencil：真人照 → Seedream I2I 彩铅图。
    返回 (compliance_prompt, candidate_image_urls)，取 urls[0] 即可。
    """
    _ = api_key, n  # pencil 路径用 config_resolver 读 Key
    url = (source_image_url or "").strip()
    if not url or not is_safe_http_url(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_image_url 须为 http(s) 或 data: URL",
        )

    mode_norm = (mode or "pencil").strip().lower()
    if mode_norm == "seedream":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="独立包仅支持 pencil 人脸合规；请使用 --face 默认 pencil",
        )

    pencil_size = (size or "4K").strip() or "4K"
    return await _run_pencil_compliance(url, size=pencil_size)
