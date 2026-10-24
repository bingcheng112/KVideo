"""人脸合规：Seedance 提示词模板与 I2I 请求体。"""
from __future__ import annotations

from typing import Any, Dict, Literal

FaceComplianceMode = Literal["pencil", "seedream"]

PENCIL_STYLE_TRANSFER_PROMPT = (
    "将照片转换为铅笔彩铅手绘风格，保留人物五官结构与发型，非写实绘画"
)


def build_pencil_style_i2i_body(
    *,
    model_name: str,
    source_image_url: str,
    prompt: str = PENCIL_STYLE_TRANSFER_PROMPT,
    size: str = "4K",
) -> Dict[str, Any]:
    """构建 Seedream I2I 请求体（对齐画布 Ark 约定）。"""
    url = (source_image_url or "").strip()
    return {
        "model": model_name,
        "prompt": (prompt or PENCIL_STYLE_TRANSFER_PROMPT).strip(),
        "image": url,
        "image_urls": [url],
        "sequential_image_generation": "disabled",
        "response_format": "url",
        "size": size,
        "stream": False,
        "watermark": False,
    }


def face_ref_anchor_text(face_ref_index: int, mode: str = "pencil") -> str:
    """生成 Seedance 视觉锚点中的人物参照描述。
    
    pencil（默认）：把风格化后的图还原成写实照片
    seedream：合规生成的人像
    """
    n = max(1, int(face_ref_index or 0))
    if (mode or "pencil").strip().lower() == "seedream":
        return f"人物参照参考图{n}（Seedream 合规生成）"
    return f"人物参照参考图{n}（把图{n}还原成写实照片风格，超写实人像摄影）"
