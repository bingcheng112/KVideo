"""口播工具：相似度计算与原片口播读取（不再用于 DNA 原文 fallback）。"""
from __future__ import annotations

import re
from typing import Union

from app.services.viral_studio.schemas import TimelineEntry


def normalize_copy_text(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[，。！？、；：…〜～—\-\"'「」【】!?.,;:'\"]+", "", t)
    return t


def similarity_ratio(a: str, b: str) -> float:
    na = normalize_copy_text(a)
    nb = normalize_copy_text(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return min(len(na), len(nb)) / max(len(na), len(nb))
    set_a = set(na)
    set_b = set(nb)
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0


def get_original_voiceover(entry: Union[TimelineEntry, dict, None]) -> str:
    if entry is None:
        return ""
    if isinstance(entry, TimelineEntry):
        audio = entry.audio
        if audio and audio.voiceover:
            return (audio.voiceover.text or "").strip()
        return ""
    audio = entry.get("audio") or {}
    vo = audio.get("voiceover") or {}
    if isinstance(vo, dict):
        return str(vo.get("text") or "").strip()
    return ""
