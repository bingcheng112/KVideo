"""Happyhorse 提示词：Seedance 结构 + [Image N] 指代。"""
from __future__ import annotations

import re

from app.services.face_compliance.prompt_templates import face_ref_anchor_text


def happyhorse_face_ref_anchor_text(face_ref_index: int) -> str:
    """Happyhorse 真人脸直连锚点（写实，无铅笔/Seedream 过审描述）。"""
    n = max(1, int(face_ref_index or 0))
    return f"人物参照参考图{n}（与参考图{n}中的出镜博主五官、发型、妆造一致）"


def to_happyhorse_image_refs(text: str) -> str:
    """参考图N / @图N / 图N / @imageN → [Image N]（高编号优先）。"""
    t = text or ""
    for n in range(9, 0, -1):
        t = t.replace(f"参考图{n}", f"[Image {n}]")
    for n in range(9, 0, -1):
        t = t.replace(f"@图{n}", f"[Image {n}]")
    for n in range(9, 0, -1):
        t = re.sub(rf"(?<!\[Image )(?<!参考)图{n}(?!\d)", f"[Image {n}]", t)
    for n in range(9, 0, -1):
        t = re.sub(rf"@image{n}\b", f"[Image {n}]", t, flags=re.IGNORECASE)
    return t


def apply_happyhorse_face_anchor(prompt: str, face_ref_index: int) -> str:
    """将 Seedance 铅笔/Seedream 人脸锚点替换为 Happyhorse 写实锚点。"""
    if not face_ref_index or face_ref_index <= 0:
        return prompt or ""
    n = max(1, int(face_ref_index))
    t = prompt or ""
    for mode in ("pencil", "seedream"):
        old = face_ref_anchor_text(n, mode)
        if old in t:
            t = t.replace(old, happyhorse_face_ref_anchor_text(n))
    # 兜底：常见 pencil 句式片段
    t = re.sub(
        rf"人物参照参考图{n}（把图{n}还原成写实照片风格，超写实人像摄影）",
        happyhorse_face_ref_anchor_text(n),
        t,
    )
    t = re.sub(
        rf"人物参照参考图{n}（Seedream 合规生成）",
        happyhorse_face_ref_anchor_text(n),
        t,
    )
    return t


def finalize_happyhorse_prompt(prompt: str, face_ref_index: int = 0) -> str:
    """Pass C 输出：人脸锚点替换 + [Image N] 指代。"""
    t = apply_happyhorse_face_anchor(prompt or "", face_ref_index)
    return to_happyhorse_image_refs(t)
