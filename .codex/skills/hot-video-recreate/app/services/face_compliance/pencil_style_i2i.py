"""铅笔彩铅风格化：Seedream 4.5 图生图。"""
from __future__ import annotations

import logging
from typing import List

from fastapi import HTTPException, status

from app.core.http_client import get_http_client
from app.services.face_compliance.config_resolver import pick_seedream45_config
from app.services.face_compliance.prompt_templates import (
    PENCIL_STYLE_TRANSFER_PROMPT,
    build_pencil_style_i2i_body,
)

logger = logging.getLogger(__name__)


def _extract_urls(response_data: dict) -> List[str]:
    urls: List[str] = []
    if not isinstance(response_data, dict):
        return urls
    items = response_data.get("data")
    if not isinstance(items, list):
        return urls
    for item in items:
        if isinstance(item, dict) and item.get("url"):
            urls.append(str(item["url"]))
    return urls


async def style_transfer_face_pencil(
    source_image_url: str,
    *,
    size: str = "4K",
) -> List[str]:
    url = (source_image_url or "").strip()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_image_url 不能为空",
        )

    target_url, model_name, api_key = await pick_seedream45_config()
    if not (api_key or "").strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="未配置 VOLC_ARK_API_KEY，无法做人脸彩铅合规",
        )

    body = build_pencil_style_i2i_body(
        model_name=model_name,
        source_image_url=url,
        prompt=PENCIL_STYLE_TRANSFER_PROMPT,
        size=size,
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    client = get_http_client()
    try:
        resp = await client.post(
            target_url,
            json=body,
            headers=headers,
            timeout=300.0,
        )
        if resp.status_code != 200:
            text = resp.text[:500]
            raise HTTPException(
                status_code=resp.status_code,
                detail=text or "Seedream 铅笔彩铅风格化失败",
            )
        response_data = resp.json()
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Seedream 铅笔彩铅 I2I 请求失败")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Seedream 铅笔彩铅风格化失败: {e}",
        ) from e

    urls = _extract_urls(response_data)
    if not urls:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Seedream 未返回图片 URL",
        )
    return urls[:1]
