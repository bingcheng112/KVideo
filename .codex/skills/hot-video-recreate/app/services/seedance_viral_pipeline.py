"""爆款复刻 Seedance 智能路由编排：Ark 低分辨率生成 → MediaKit 标准超分。"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict

from app.services.seedance_utils import (
    extract_task_status,
    extract_usage_tokens,
    extract_video_url,
    is_terminal_failed,
    is_terminal_state,
    is_terminal_success,
)
from app.services.seedance_mini_1080_ark import (
    create_task,
    extract_duration_sec,
    extract_last_frame_url,
    get_task,
)
from app.services.seedance_mini_1080_errors import map_ark_failure, map_enhance_failure
from app.services.seedance_viral_jobs import get_job, update_job
from app.services.volc_imp_enhance import enhance_video_standard

logger = logging.getLogger(__name__)

ARK_POLL_INTERVAL = 5.0
ARK_POLL_TIMEOUT = 1800.0  # 30 分钟
DISPLAY_MODEL = "seedance-2.0"


def _parse_request_json(job: Dict[str, Any]) -> Dict[str, Any]:
    raw = job.get("request_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


async def _poll_ark_until_done(ark_task_id: str) -> Dict[str, Any]:
    deadline = time.time() + ARK_POLL_TIMEOUT
    last_data: Dict[str, Any] = {}
    while time.time() < deadline:
        data = await get_task(ark_task_id)
        last_data = data
        st = extract_task_status(data)
        if is_terminal_state(st, data):
            return data
        await asyncio.sleep(ARK_POLL_INTERVAL)
    raise RuntimeError("方舟视频生成超时，请缩短时长或稍后重试")


async def run_viral_job_pipeline(job_id: str) -> None:
    job = await get_job(job_id)
    if not job:
        return
    req = _parse_request_json(job)
    fallback_duration = int(job.get("duration_sec") or 8)

    try:
        await update_job(job_id, status="ark_running")
        ark_task_id = await create_task(req)
        await update_job(job_id, ark_task_id=ark_task_id)

        ark_data = await _poll_ark_until_done(ark_task_id)
        st = extract_task_status(ark_data)

        if is_terminal_failed(st, ark_data):
            raw_err = str(ark_data.get("error") or ark_data.get("message") or st)
            msg, hint = map_ark_failure(raw_err)
            await update_job(
                job_id,
                status="ark_failed",
                error_stage="ark",
                error_message=msg,
                retry_hint=hint,
            )
            return

        if not is_terminal_success(st, ark_data):
            msg, hint = map_ark_failure("任务未成功完成")
            await update_job(
                job_id,
                status="ark_failed",
                error_stage="ark",
                error_message=msg,
                retry_hint=hint,
            )
            return

        video_raw = extract_video_url(ark_data)
        if not video_raw:
            msg, hint = map_ark_failure("任务成功但未返回视频地址")
            await update_job(
                job_id,
                status="ark_failed",
                error_stage="ark",
                error_message=msg,
                retry_hint=hint,
            )
            return

        usage_tokens = extract_usage_tokens(ark_data)
        duration_sec = extract_duration_sec(ark_data, fallback_duration)
        last_frame = extract_last_frame_url(ark_data)

        await update_job(
            job_id,
            video_url_raw=video_raw,
            last_frame_url=last_frame,
            usage_tokens=usage_tokens,
            duration_sec=duration_sec,
            status="enhance_running",
        )

        try:
            enhance_task_id, video_enhanced = await enhance_video_standard(
                video_raw, job.get("enhance_target") or "1080p"
            )
            await update_job(
                job_id,
                status="completed",
                enhance_task_id=enhance_task_id,
                video_url_enhanced=video_enhanced,
                error_stage=None,
                error_message=None,
                retry_hint=None,
            )
        except Exception as e:
            logger.exception("[viral_seedance] enhance failed job=%s", job_id)
            msg, hint = map_enhance_failure(str(e))
            await update_job(
                job_id,
                status="partial_success",
                error_stage="enhance",
                error_message=msg,
                retry_hint=hint,
            )

    except Exception as e:
        logger.exception("[viral_seedance] pipeline failed job=%s", job_id)
        msg, hint = map_ark_failure(str(e))
        await update_job(
            job_id,
            status="ark_failed",
            error_stage="ark",
            error_message=msg,
            retry_hint=hint,
        )


def job_to_response(job: Dict[str, Any]) -> Dict[str, Any]:
    status = str(job.get("status") or "")
    video_raw = job.get("video_url_raw")
    video_enhanced = job.get("video_url_enhanced")
    if status == "completed":
        primary_url = video_enhanced
    elif status == "partial_success":
        primary_url = video_raw
    else:
        primary_url = None
    return {
        "job_id": job.get("job_id"),
        "status": status,
        "video_url": primary_url,
        "video_url_raw": video_raw,
        "video_url_enhanced": video_enhanced,
        "last_frame_url": job.get("last_frame_url"),
        "resolved_model": job.get("resolved_model"),
        "involves_real_person": bool(job.get("involves_real_person")),
        "has_face_ref": bool(job.get("has_face_ref")),
        "error_stage": job.get("error_stage"),
        "error_message": job.get("error_message"),
        "retry_hint": job.get("retry_hint"),
        "segment_index": job.get("segment_index"),
        "source": job.get("source"),
    }
