"""viral-studio Chat 模型配置：从环境变量读取（独立包，不读 MySQL）。"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Tuple

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

ENV_OMNI_MODEL = "VOLC_OMNI_MODEL"
ENV_PLUS_MODEL = "VOLC_PLUS_MODEL"
ENV_OMNI_URL = "VOLC_OMNI_URL"
ENV_PLUS_URL = "VOLC_PLUS_URL"
ENV_API_KEY = "DASHSCOPE_API_KEY"

_DEFAULT_OMNI_MODEL = "qwen3.5-omni-plus"
_DEFAULT_PLUS_MODEL = "qwen3.5-plus"
_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _env_or(key: str, default: str) -> str:
    return (os.environ.get(key) or "").strip() or default


def _require_api_key() -> str:
    key = (os.environ.get(ENV_API_KEY) or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="未配置 DASHSCOPE_API_KEY，请在 .env 中填写",
        )
    return key


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


async def pick_omni_config() -> Tuple[Dict[str, Any], str, str]:
    _require_api_key()
    base_url = _env_or(ENV_OMNI_URL, _DEFAULT_BASE_URL)
    target_url = _chat_completions_url(base_url)
    model_name = _env_or(ENV_OMNI_MODEL, _DEFAULT_OMNI_MODEL)
    cfg: Dict[str, Any] = {
        "name": "env-omni",
        "provider": model_name,
        "base_url": base_url,
        "canvas_model_id": model_name,
    }
    return cfg, target_url, model_name


async def pick_plus_config() -> Tuple[Dict[str, Any], str, str]:
    _require_api_key()
    base_url = _env_or(ENV_PLUS_URL, _DEFAULT_BASE_URL)
    target_url = _chat_completions_url(base_url)
    model_name = _env_or(ENV_PLUS_MODEL, _DEFAULT_PLUS_MODEL)
    cfg: Dict[str, Any] = {
        "name": "env-plus",
        "provider": model_name,
        "base_url": base_url,
        "canvas_model_id": model_name,
    }
    return cfg, target_url, model_name
