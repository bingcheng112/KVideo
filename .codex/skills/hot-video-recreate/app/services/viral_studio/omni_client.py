"""qwen3.5-omni-plus 流式 Chat 客户端。"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.database import db
from app.core.http_client import get_http_client
from app.routers.canvas_proxy import (
    get_api_key_for_target,
    log_canvas_consumption,
    refund_reserved_credits,
    try_reserve_credits,
)
from app.services.canvas_chat_billing import estimate_prompt_tokens_from_messages
from app.services.viral_studio.billing import (
    estimate_omni_reserve_cost,
    settle_chat_cost_generic,
)

logger = logging.getLogger(__name__)


async def _aggregate_stream_response(resp) -> Tuple[str, Dict[str, Any]]:
    """聚合 SSE stream 为完整文本 + usage。"""
    chunks: List[str] = []
    usage: Dict[str, Any] = {}
    async for line in resp.aiter_lines():
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(obj.get("usage"), dict):
            usage = obj["usage"]
        choices = obj.get("choices") or []
        if choices and isinstance(choices[0], dict):
            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                chunks.append(str(content))
    return "".join(chunks), usage


async def chat_completion_stream(
    user_id: str,
    *,
    target_url: str,
    model_name: str,
    messages: List[Dict[str, Any]],
    max_tokens: int = 8192,
    video_seconds: int = 0,
    consumption_remark: str = "viral-studio",
) -> Tuple[str, Dict[str, Any], int, int]:
    """
    调用 Omni/Plus Chat（stream=true），返回 (content, response_for_billing, cost, balance)。
    """
    api_key = (await get_api_key_for_target(target_url) or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat API 密钥未配置",
        )

    body: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "max_tokens": max_tokens,
        "stream_options": {"include_usage": True},
        "modalities": ["text"],
    }
    modalities = body.get("modalities") or ["text"]
    text_only_output = "audio" not in modalities

    cost = estimate_omni_reserve_cost(
        body,
        model_name,
        video_seconds=video_seconds,
        max_completion_tokens=max_tokens,
        text_only_output=text_only_output,
    )
    pending_refund = False
    if cost > 0:
        if not await try_reserve_credits(user_id, cost, db):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"算力不足，需要 {cost} 算力，请充值后再试",
            )
        pending_refund = True

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    timeout = float(getattr(settings, "CANVAS_PROXY_TIMEOUT_SECONDS", 300))
    if video_seconds > 30:
        timeout = max(timeout, 600.0)

    client = get_http_client()
    try:
        async with client.stream(
            "POST",
            target_url,
            json=body,
            headers=headers,
            timeout=timeout,
        ) as resp:
            if resp.status_code != 200:
                text = (await resp.aread()).decode("utf-8", errors="replace")[:500]
                if pending_refund:
                    await refund_reserved_credits(user_id, cost, db)
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=text or "上游返回错误",
                )
            content, usage = await _aggregate_stream_response(resp)
    except HTTPException:
        raise
    except Exception as e:
        if pending_refund:
            await refund_reserved_credits(user_id, cost, db)
        logger.exception("viral-studio Chat 请求失败")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Chat 请求失败: {e}",
        ) from e

    response_data = {"usage": usage}
    text_prompt_tokens = estimate_prompt_tokens_from_messages(body)
    actual_cost, pt, ct = await settle_chat_cost_generic(
        user_id,
        cost,
        model_name,
        response_data,
        db,
        video_seconds=video_seconds,
        text_only_output=text_only_output,
        text_prompt_tokens=text_prompt_tokens,
    )
    if actual_cost > 0:
        await log_canvas_consumption(
            user_id,
            actual_cost,
            db,
            model_name,
            "Chat",
            prompt_tokens=pt,
            completion_tokens=ct,
            usage_data=usage,
            text_only_output=text_only_output,
        )

    row = await db.execute_one(
        "SELECT credits FROM users WHERE id = %s",
        (user_id,),
    )
    balance = int(row.get("credits") or 0) if row else 0
    return content, response_data, actual_cost, balance
