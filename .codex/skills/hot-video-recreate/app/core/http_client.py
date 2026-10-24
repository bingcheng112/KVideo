"""独立包 stub：全局 HTTP 客户端（按需自动初始化）。"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_http_client: Optional[httpx.AsyncClient] = None


def init_http_client() -> None:
    global _http_client
    if _http_client is not None:
        return
    _http_client = httpx.AsyncClient(
        timeout=300.0,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        http2=False,
    )


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        init_http_client()
    assert _http_client is not None
    return _http_client


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
