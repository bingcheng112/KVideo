"""全片口播唯一性：normalize、检测重复、收集已用口播（供 Pass B coherence / scene_fix）。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.services.viral_studio.schemas import AdaptedScene, AdaptedScript

_PUNCT_MAP = str.maketrans(
    {
        "，": ",",
        "。": ".",
        "！": "!",
        "？": "?",
        "；": ";",
        "：": ":",
        "「": "",
        "」": "",
        "『": "",
        "』": "",
        "“": "",
        "”": "",
        "‘": "",
        "’": "",
        "…": "...",
    }
)


def normalize_vo_text(text: str) -> str:
    """strip、合并空白、统一标点，供比较是否同一句。"""
    t = (text or "").strip()
    if not t:
        return ""
    t = t.translate(_PUNCT_MAP)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[,.!?;:\s]+$", "", t)
    return t.strip()


def effective_voiceover(scene: AdaptedScene) -> str:
    """performed > semantic > new_voiceover。"""
    if scene.six:
        performed = (scene.six.audio.voiceover_performed or "").strip()
        if performed:
            return performed
        semantic = (scene.six.audio.voiceover_semantic or "").strip()
        if semantic:
            return semantic
    return (scene.new_voiceover or "").strip()


def scene_duration_sec(scene: AdaptedScene) -> float:
    start = float(scene.start_sec or 0)
    end = float(scene.end_sec or 0)
    if end > start:
        return end - start
    return 0.0


def find_duplicate_voiceover_scene_ids(script: AdaptedScript) -> List[int]:
    """按 adapted_script 顺序；返回第二次及以后重复出现的 scene_id。"""
    seen: Dict[str, int] = {}
    duplicates: List[int] = []
    for scene in script.adapted_script or []:
        vo = normalize_vo_text(effective_voiceover(scene))
        if not vo:
            continue
        sid = int(scene.scene_id or 0)
        if vo in seen:
            if sid and sid not in duplicates:
                duplicates.append(sid)
        else:
            seen[vo] = sid
    return duplicates


def collect_used_voiceovers(
    script: AdaptedScript,
    *,
    exclude_scene_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """供 scene_fix：已用口播列表（不含 exclude_scene_id）。"""
    items: List[Dict[str, Any]] = []
    for scene in script.adapted_script or []:
        sid = int(scene.scene_id or 0)
        if exclude_scene_id is not None and sid == exclude_scene_id:
            continue
        vo = effective_voiceover(scene)
        if not vo:
            continue
        items.append(
            {
                "scene_id": sid,
                "text": vo,
                "start_sec": float(scene.start_sec or 0),
                "end_sec": float(scene.end_sec or 0),
            }
        )
    return items
