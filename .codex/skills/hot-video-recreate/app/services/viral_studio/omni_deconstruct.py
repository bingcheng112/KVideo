"""Pass A：视频全模态拆解。"""
from __future__ import annotations

import logging
from typing import List, Tuple

from app.core.url_safety import is_safe_http_url
from app.services.viral_studio.content_profile import build_content_profile
from app.services.viral_studio.config_resolver import pick_omni_config
from app.services.viral_studio.json_utils import parse_json_object
from app.services.viral_studio.omni_client import chat_completion_stream
from app.services.viral_studio.prompts.deconstruct import DECONSTRUCT_SYSTEM, deconstruct_user_text
from app.services.viral_studio.schemas import UsageInfo, VideoDNA
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

_USER_FRIENDLY_DECONSTRUCT_FAIL = "视频拆解失败，请稍后重试"

DECONSTRUCT_FPS_SINGLE_SEGMENT = 6
DECONSTRUCT_FPS_SHORT = 4
DECONSTRUCT_FPS_DEFAULT = 3
DECONSTRUCT_FPS_SINGLE_SEGMENT_MAX_SEC = 15
DECONSTRUCT_FPS_SHORT_MAX_SEC = 30


def _deconstruct_fps(video_seconds: int) -> int:
    if video_seconds <= DECONSTRUCT_FPS_SINGLE_SEGMENT_MAX_SEC:
        return DECONSTRUCT_FPS_SINGLE_SEGMENT
    if video_seconds <= DECONSTRUCT_FPS_SHORT_MAX_SEC:
        return DECONSTRUCT_FPS_SHORT
    return DECONSTRUCT_FPS_DEFAULT


def _validate_dna(dna: VideoDNA) -> List[str]:
    """轻量校验拆解质量，返回问题列表（不阻断）。"""
    issues: List[str] = []
    duration = float(dna.meta.duration_sec or 0)
    if duration <= 0 and dna.timeline:
        duration = max(float(e.end) for e in dna.timeline)

    timeline = dna.timeline or []
    if duration > 0 and timeline:
        pace = (dna.rhythm.pace or "").strip()
        is_fast = "快" in pace
        min_shots = max(1, int(duration / 5) if is_fast else int(duration / 8))
        if len(timeline) < min_shots:
            issues.append(
                f"timeline 镜数 {len(timeline)} 少于期望 {min_shots}（duration={duration}s, pace={pace or '未知'}）"
            )

        for i, entry in enumerate(timeline):
            vis = entry.visual or {}
            camera = str(vis.get("camera") or "").strip()
            if not camera:
                issues.append(f"timeline[{i}] visual.camera 为空")
            elif "固定机位" in camera and "人物居中" in camera:
                issues.append(f"timeline[{i}] visual.camera 过于笼统：{camera}")

        if timeline:
            first_start = float(timeline[0].start)
            last_end = float(timeline[-1].end)
            if first_start > 0.5:
                issues.append(f"timeline 未从 0 开始（首镜 start={first_start}）")
            if duration > 0 and last_end < duration - 0.5:
                issues.append(f"timeline 未覆盖全片（末镜 end={last_end}, duration={duration}）")

        transitions = dna.transitions or []
        beats = dna.rhythm.beat_points_sec or []
        if transitions and len(beats) < len(transitions):
            issues.append(
                f"beat_points_sec 数量 {len(beats)} 少于 transitions 数量 {len(transitions)}"
            )

        for i, entry in enumerate(timeline):
            audio = entry.audio
            vo = audio.voiceover if audio else None
            if vo and vo.text:
                if not (vo.text or "").strip():
                    issues.append(f"timeline[{i}] 有口播标记但 text 为空")

    return issues


async def deconstruct_video(
    user_id: str,
    *,
    reference_video_url: str,
    reference_video_seconds: int = 0,
) -> Tuple[VideoDNA, UsageInfo, int, int]:
    url = (reference_video_url or "").strip()
    if not is_safe_http_url(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reference_video_url 须为可访问的 http(s) 公网地址",
        )

    _cfg, target_url, model_name = await pick_omni_config()
    secs = max(1, int(reference_video_seconds or 30))

    fps = _deconstruct_fps(secs)

    messages = [
        {"role": "system", "content": DECONSTRUCT_SYSTEM},
        {
            "role": "user",
            "content": [
                {"type": "video_url", "video_url": {"url": url}, "fps": fps},
                {"type": "text", "text": deconstruct_user_text()},
            ],
        },
    ]

    raw, resp_data, cost, balance = await chat_completion_stream(
        user_id,
        target_url=target_url,
        model_name=model_name,
        messages=messages,
        max_tokens=8192,
        video_seconds=secs,
        consumption_remark="viral-studio-deconstruct",
    )

    try:
        data = parse_json_object(raw)
    except Exception as e:
        logger.warning("Video DNA JSON 语法解析失败: %s raw=%s", e, raw[:2000])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_USER_FRIENDLY_DECONSTRUCT_FAIL,
        ) from e

    try:
        dna = VideoDNA.from_dict(data)
    except Exception as e:
        logger.warning("Video DNA schema 校验失败: %s data=%s", e, str(data)[:2000])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_USER_FRIENDLY_DECONSTRUCT_FAIL,
        ) from e

    usage = resp_data.get("usage") or {}
    usage_info = UsageInfo(
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )
    if dna.meta.duration_sec <= 0 and secs > 0:
        dna.meta.duration_sec = float(secs)

    validation_issues = _validate_dna(dna)
    if validation_issues:
        logger.warning("Video DNA 质量校验提示: %s", "; ".join(validation_issues))

    profile = build_content_profile(dna)
    logger.info(
        "Video DNA content profile: voiceover=%s person=%s mode=%s",
        profile.has_voiceover,
        profile.has_on_screen_person,
        profile.voiceover_mode.value,
    )

    return dna, usage_info, cost, balance
