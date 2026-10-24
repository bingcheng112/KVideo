"""爆款复刻 Seedance 智能路由 Job 持久化（本地 JSON 文件）。"""
from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 包根目录下的 .seedance_data（app/services → 上两级到包根）
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
_DATA_DIR = os.path.join(_PKG_ROOT, ".seedance_data")
_JOBS_FILE = os.path.join(_DATA_DIR, "viral_jobs.json")


def _ensure_data_dir() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)


def _read_jobs() -> Dict[str, Any]:
    _ensure_data_dir()
    if not os.path.exists(_JOBS_FILE):
        return {}
    try:
        with open(_JOBS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _write_jobs(jobs: Dict[str, Any]) -> None:
    _ensure_data_dir()
    with open(_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def new_job_id() -> str:
    return f"vsd-{uuid.uuid4().hex}"


async def create_job(
    *,
    job_id: str,
    user_id: str,
    duration_sec: int,
    user_resolution: str,
    gen_resolution: str,
    enhance_target: str,
    resolved_model: str,
    involves_real_person: bool,
    has_face_ref: bool,
    source: str,
    segment_index: Optional[int],
    request_json: Dict[str, Any],
) -> None:
    jobs = _read_jobs()
    import time
    jobs[job_id] = {
        "job_id": job_id,
        "user_id": user_id,
        "status": "pending",
        "duration_sec": int(duration_sec),
        "usage_tokens": None,
        "user_resolution": user_resolution,
        "gen_resolution": gen_resolution,
        "enhance_target": enhance_target,
        "resolved_model": resolved_model,
        "involves_real_person": bool(involves_real_person),
        "has_face_ref": bool(has_face_ref),
        "ark_task_id": None,
        "enhance_task_id": None,
        "video_url_raw": None,
        "video_url_enhanced": None,
        "last_frame_url": None,
        "error_stage": None,
        "error_message": None,
        "retry_hint": None,
        "source": source,
        "segment_index": segment_index,
        "request_json": json.dumps(request_json, ensure_ascii=False),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write_jobs(jobs)


async def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    jobs = _read_jobs()
    return jobs.get(job_id)


async def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    import time
    jobs = _read_jobs()
    if job_id not in jobs:
        return
    if "updated_at" not in fields:
        fields["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    jobs[job_id].update(fields)
    _write_jobs(jobs)
