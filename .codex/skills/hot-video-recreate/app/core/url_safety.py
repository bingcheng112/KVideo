"""独立包：URL 安全校验（允许 http(s) 与 data:）。"""
from __future__ import annotations

from urllib.parse import urlparse


def is_safe_http_url(url: str) -> bool:
    s = (url or "").strip()
    if not s:
        return False
    if s.startswith("data:"):
        return True
    try:
        p = urlparse(s)
    except Exception:
        return False
    if p.scheme not in ("http", "https"):
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    if host in ("localhost", "127.0.0.1", "0.0.0.0"):
        return False
    if host.endswith(".local"):
        return False
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        a, b, c, d = (int(x) for x in parts)
        if a == 10:
            return False
        if a == 192 and b == 168:
            return False
        if a == 172 and 16 <= b <= 31:
            return False
        if a == 127:
            return False
        if a == 169 and b == 254:
            return False
    return True
