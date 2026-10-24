"""独立包 stub：应用配置。"""
from __future__ import annotations

import os


class _Settings:
    CANVAS_PROXY_TIMEOUT_SECONDS: float = float(
        os.environ.get("CANVAS_PROXY_TIMEOUT_SECONDS") or 300
    )


settings = _Settings()
