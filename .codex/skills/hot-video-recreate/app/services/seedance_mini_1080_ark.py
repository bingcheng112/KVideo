"""服务端调用火山方舟 Seedance（720P 创建/查询）。"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

import httpx

from app.core.http_client import get_http_client
from app.routers.canvas_proxy import get_api_key_for_target
from app.services.seedance_utils import extract_ark_task_id_from_response

ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
_HAOYA_PREFIX = "_haoya_"


def _strip_internal_fields(body: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(body)
    haoya_res = out.get("_haoya_output_resolution")
    if haoya_res is not None and str(haoya_res).strip() and "resolution" not in out:
        out["resolution"] = str(haoya_res).strip()
    for k in list(out.keys()):
        if str(k).startswith(_HAOYA_PREFIX):
            out.pop(k, None)
    return out


async def _ark_headers() -> Dict[str, str]:
    api_key = (await get_api_key_for_target(ARK_BASE) or "").strip()
    if not api_key:
        raise RuntimeError("未配置方舟 API Key，请在管理端 api_configs 中添加 ark.cn-beijing.volces.com")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


async def create_task(body: Dict[str, Any]) -> str:
    client = get_http_client()
    payload = _strip_internal_fields(body)
    url = f"{ARK_BASE}/contents/generations/tasks"
    try:
        resp = await client.post(url, headers=await _ark_headers(), json=payload, timeout=120.0)
    except httpx.HTTPError as e:
        raise RuntimeError(f"方舟创建任务失败: {e}") from e
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"方舟响应非 JSON ({resp.status_code}): {(resp.text or '')[:300]}")
    if resp.status_code >= 400:
        msg = data.get("error", data) if isinstance(data, dict) else resp.text
        raise RuntimeError(str(msg)[:500])
    task_id = extract_ark_task_id_from_response(data)
    if not task_id:
        raise RuntimeError("方舟未返回 task_id")
    return task_id


async def get_task(ark_task_id: str) -> Dict[str, Any]:
    client = get_http_client()
    url = f"{ARK_BASE}/contents/generations/tasks/{ark_task_id}"
    try:
        resp = await client.get(url, headers=await _ark_headers(), timeout=120.0)
    except httpx.HTTPError as e:
        raise RuntimeError(f"方舟查询任务失败: {e}") from e
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"方舟查询响应非 JSON ({resp.status_code})")
    if resp.status_code >= 400:
        raise RuntimeError((resp.text or "")[:500])
    if not isinstance(data, dict):
        raise RuntimeError("方舟响应格式异常")
    return data


def extract_last_frame_url(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    o = data.get("output") if isinstance(data.get("output"), dict) else data
    c = data.get("content")
    candidates: List[Any] = [
        data.get("last_frame_url"),
        o.get("last_frame_url") if isinstance(o, dict) else None,
        c.get("last_frame_url") if isinstance(c, dict) else None,
        data.get("result", {}).get("last_frame_url") if isinstance(data.get("result"), dict) else None,
    ]
    if isinstance(o, dict) and isinstance(o.get("results"), list) and o["results"]:
        first = o["results"][0]
        if isinstance(first, dict):
            candidates.append(first.get("last_frame_url"))
    for val in candidates:
        if isinstance(val, str) and val.startswith(("http://", "https://")):
            return val.strip()
    return None


def extract_duration_sec(data: Any, fallback: int) -> int:
    if not isinstance(data, dict):
        return max(1, int(fallback))
    for key in ("duration", "video_duration"):
        v = data.get(key)
        if isinstance(v, (int, float)) and v > 0:
            return max(1, int(v))
    content = data.get("content")
    if isinstance(content, dict):
        v = content.get("duration")
        if isinstance(v, (int, float)) and v > 0:
            return max(1, int(v))
    return max(1, int(fallback))
