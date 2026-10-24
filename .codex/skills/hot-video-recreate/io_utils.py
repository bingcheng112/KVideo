"""本地文件 / URL 规范化：路径转 data URL，探测视频时长。"""
from __future__ import annotations

import base64
import mimetypes
import os
import subprocess
from typing import Optional
from urllib.parse import urlparse

VIDEO_SOFT_LIMIT_BYTES = 25 * 1024 * 1024

_VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
}

_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def is_http_url(value: str) -> bool:
    try:
        p = urlparse((value or "").strip())
    except Exception:
        return False
    return p.scheme in ("http", "https") and bool(p.netloc)


def _file_to_data_url(path: str, mime: str) -> str:
    abs_path = os.path.abspath(path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(f"文件不存在: {abs_path}")
    with open(abs_path, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def resolve_media_ref(value: str, *, kind: str = "image") -> str:
    """
    返回可供 Omni/Plus 使用的 URL：
    - 已是 http(s) → 原样
    - 本地路径 → data URL
    """
    s = (value or "").strip()
    if not s:
        raise ValueError("媒体路径为空")
    if is_http_url(s) or s.startswith("data:"):
        return s
    path = os.path.abspath(s)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"文件不存在: {path}")
    ext = os.path.splitext(path)[1].lower()
    if kind == "video":
        mime = _VIDEO_MIME.get(ext) or mimetypes.guess_type(path)[0] or "video/mp4"
        size = os.path.getsize(path)
        if size > VIDEO_SOFT_LIMIT_BYTES:
            mb = size / (1024 * 1024)
            print(
                f"[warn] 本地视频约 {mb:.1f}MB，超过建议 25MB；"
                f"data URL 可能失败，建议改用公网 http(s) URL: {path}"
            )
    else:
        mime = _IMAGE_MIME.get(ext) or mimetypes.guess_type(path)[0] or "image/jpeg"
    return _file_to_data_url(path, mime)


def probe_video_seconds(path_or_url: str) -> Optional[float]:
    """用 ffprobe 探测时长；失败返回 None。"""
    s = (path_or_url or "").strip()
    if not s or s.startswith("data:"):
        return None
    target = s if is_http_url(s) else os.path.abspath(s)
    if not is_http_url(target) and not os.path.isfile(target):
        return None
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                target,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode != 0:
            return None
        line = (proc.stdout or "").strip().splitlines()
        if not line:
            return None
        return float(line[0])
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        return None
