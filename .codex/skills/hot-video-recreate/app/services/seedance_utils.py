"""Seedance 2.0 工具函数：模型识别、方舟响应解析、终端状态判断等。
提取自原 seedance_utils.py，去掉了计费/credits 相关代码。
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Tuple


# ── 模型识别 ──────────────────────────────────────

def resolve_seedance_variant(model_hint: str) -> Optional[str]:
    h = (model_hint or "").lower()
    if "mini" in h:
        return "mini"
    if "fast" in h:
        return "fast"
    return None


def is_seedance_mini_model(model_hint: str) -> bool:
    return resolve_seedance_variant(model_hint) == "mini"


def is_seedance_fast_model(model_hint: str) -> bool:
    return resolve_seedance_variant(model_hint) == "fast"


def is_seedance_720_only_model(model_hint: str) -> bool:
    return resolve_seedance_variant(model_hint) is not None


# ── 终端状态判断 ──────────────────────────────────

_TERMINAL_SUCCESS = frozenset(
    {"succeeded", "success", "finished", "completed", "done"}
)
_TERMINAL_FAILED = frozenset(
    {"failed", "failure", "error", "cancelled", "canceled", "expired", "unknown"}
)


def is_terminal_success(status: str, data: Any) -> bool:
    st = (status or "").lower()
    if st in _TERMINAL_SUCCESS:
        return True
    if isinstance(data, dict):
        for key in ("status", "task_status"):
            v = str(data.get(key) or "").lower()
            if v in _TERMINAL_SUCCESS:
                return True
    return False


def is_terminal_failed(status: str, data: Any) -> bool:
    st = (status or "").lower()
    if st in _TERMINAL_FAILED:
        return True
    if isinstance(data, dict):
        for key in ("status", "task_status"):
            v = str(data.get(key) or "").lower()
            if v in _TERMINAL_FAILED:
                return True
    return False


def is_terminal_state(status: str, data: Any) -> bool:
    return is_terminal_success(status, data) or is_terminal_failed(status, data)


# ── 方舟响应解析 ──────────────────────────────────

def _ceil_div(n: int, d: int) -> int:
    if d <= 0:
        return 0
    return (n + d - 1) // d


def billing_video_seconds(value: Any, *, default: int = 0, min_one: bool = False) -> int:
    """秒数向上取整；min_one=True 时至少 1（用于输出时长）。"""
    try:
        if value is None:
            base = max(0, int(default))
        else:
            f = float(value)
            if not math.isfinite(f) or f <= 0:
                base = max(0, int(default))
            else:
                base = int(math.ceil(f))
    except (TypeError, ValueError):
        base = max(0, int(default))
    if min_one:
        return max(1, base)
    return max(0, base)


def extract_ark_task_id_from_response(data: Any) -> Optional[str]:
    if isinstance(data, dict):
        for key in ("id", "task_id"):
            v = data.get(key)
            if v is not None and str(v).strip():
                return str(v).strip()
        inner = data.get("data")
        if isinstance(inner, dict):
            return extract_ark_task_id_from_response(inner)
    return None


def extract_ark_task_id_from_url(target_url: str) -> Optional[str]:
    if not target_url:
        return None
    m = re.search(r"/contents/generations/tasks/([^/?#]+)", target_url)
    if m:
        tid = m.group(1).strip()
        return tid if tid else None
    return None


def extract_dashscope_task_id_from_response(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    task = data.get("task")
    if isinstance(task, dict):
        for key in ("task_id", "id"):
            v = task.get(key)
            if v is not None and str(v).strip():
                return str(v).strip()
    data_output = data.get("output")
    if isinstance(data_output, dict):
        task = data_output.get("task")
        if isinstance(task, dict):
            v = task.get("task_id") or task.get("id")
            if v is not None and str(v).strip():
                return str(v).strip()
    task = data.get("task")
    if isinstance(task, dict):
        v = task.get("task_id") or task.get("id")
        if v is not None and str(v).strip():
            return str(v).strip()
    inner = data.get("data")
    if isinstance(inner, dict):
        return extract_dashscope_task_id_from_response(inner)
    return None


def extract_dashscope_task_id_from_url(target_url: str) -> Optional[str]:
    if not target_url:
        return None
    m = re.search(r"/api/v1/tasks/([^/?#]+)", target_url, re.I)
    if m:
        tid = m.group(1).strip()
        return tid if tid else None
    return None


def extract_task_status(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("status", "task_status", "state"):
        v = data.get(key)
        if v is not None and str(v).strip():
            return str(v).strip().lower()
    task = data.get("task")
    if isinstance(task, dict):
        st = extract_task_status(task)
        if st:
            return st
    output = data.get("output")
    if isinstance(output, dict):
        st = extract_task_status(output)
        if st:
            return st
    inner = data.get("data")
    if isinstance(inner, dict):
        st = extract_task_status(inner)
        if st:
            return st
    return ""


def extract_usage_tokens(response_data: Any) -> int:
    if not isinstance(response_data, dict):
        return 0
    usage = response_data.get("usage")
    if not isinstance(usage, dict):
        task = response_data.get("task")
        if isinstance(task, dict):
            usage = task.get("usage")
    if not isinstance(usage, dict):
        inner = response_data.get("data")
        if isinstance(inner, dict):
            return extract_usage_tokens(inner)
        return 0
    for key in ("total_tokens", "completion_tokens", "prompt_tokens"):
        v = usage.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return int(v)
    return 0


def extract_video_url(response_data: Any) -> Optional[str]:
    """与前端 pickVolcArkContentGenVideoUrl 路径一致。"""
    if not isinstance(response_data, dict):
        return None

    def pick(d: Dict[str, Any]) -> Optional[str]:
        o = d.get("output") if isinstance(d.get("output"), dict) else d
        if not isinstance(o, dict):
            o = d
        candidates: List[Any] = [
            d.get("video_url"),
            o.get("video_url") if isinstance(o, dict) else None,
        ]
        content = d.get("content")
        if isinstance(content, dict):
            candidates.extend([content.get("video_url"), content.get("url")])
        result = d.get("result")
        if isinstance(result, dict):
            candidates.extend([result.get("video_url"), result.get("url")])
        if isinstance(o, dict):
            candidates.extend([o.get("url")])
            video = o.get("video")
            if isinstance(video, dict):
                candidates.append(video.get("url"))
            results = o.get("results")
            if isinstance(results, list) and results and isinstance(results[0], dict):
                candidates.extend([results[0].get("url"), results[0].get("video_url")])
        for c in candidates:
            if isinstance(c, str) and c.strip().startswith(("http://", "https://")):
                return c.strip()
        return None

    url = pick(response_data)
    if url:
        return url
    inner = response_data.get("data")
    if isinstance(inner, dict):
        return extract_video_url(inner)
    return None


def parse_seedance_create_body(body: Dict[str, Any]) -> Dict[str, Any]:
    """解析创建请求体，标准化字段。"""
    return {
        "model": str(body.get("model") or ""),
        "content": body.get("content") or body.get("input") or {},
        "duration": int(body.get("duration") or 0),
        "resolution": str(body.get("resolution") or body.get("size") or "720P"),
    }


def _is_seedance_query_url(target_url: str) -> bool:
    low = (target_url or "").lower()
    return "/contents/generations/tasks/" in low


def is_seedance_video_request(
    target_url: str, method: str, model_hint: str, body: Optional[Dict[str, Any]] = None
) -> bool:
    """POST 创建或 GET 查询 Seedance 任务。"""
    low_url = (target_url or "").lower()
    if "/contents/generations/tasks" not in low_url:
        return False
    if (method or "").upper() == "GET" and _is_seedance_query_url(target_url):
        return True
    if (method or "").upper() != "POST":
        return False
    h = (model_hint or "").lower()
    if "doubao-seedance-2" in h:
        return True
    if "seedance-2" in h or "seedance2" in h:
        return True
    if isinstance(body, dict):
        bm = str(body.get("model") or "").lower()
        if "doubao-seedance-2" in bm or "seedance-2" in bm or "seedance2" in bm:
            return True
    return False


def estimate_duration_sec(ark_body: dict) -> int:
    return billing_video_seconds((ark_body or {}).get('duration'), default=8, min_one=True)

