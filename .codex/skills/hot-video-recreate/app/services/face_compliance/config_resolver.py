"""Face compliance 模型配置：从环境变量读取。"""
from __future__ import annotations

import os
from typing import Tuple

_ENV_SEEDREAM45_MODEL = "VOLC_SEEDREAM45_MODEL"
_ENV_IMAGE_URL = "VOLC_IMAGE_URL"
_ENV_API_KEY_ARK = "VOLC_ARK_API_KEY"

_DEFAULT_SEEDREAM45_MODEL = "doubao-seedream-4-5-251128"
_DEFAULT_ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def _env_or(key: str, default: str) -> str:
    return (os.environ.get(key) or "").strip() or default


async def pick_seedream45_config() -> Tuple[str, str, str]:
    """Seedream I2I：/images/generations"""
    base_url = _env_or(_ENV_IMAGE_URL, _DEFAULT_ARK_BASE_URL)
    target_url = f"{base_url.rstrip('/')}/images/generations"
    model_name = _env_or(_ENV_SEEDREAM45_MODEL, _DEFAULT_SEEDREAM45_MODEL)
    api_key = _env_or(_ENV_API_KEY_ARK, "")
    return target_url, model_name, api_key
