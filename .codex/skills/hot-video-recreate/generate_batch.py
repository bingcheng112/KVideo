"""逐段 Seedance 生成：路由 + 可选尾帧链 + 下载 mp4。"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.http_client import get_http_client
from app.services.seedance_viral_jobs import create_job, get_job, new_job_id
from app.services.seedance_viral_pipeline import run_viral_job_pipeline
from app.services.seedance_viral_routing import (
    normalize_user_resolution,
    resolve_ark_model_async,
    resolve_gen_and_enhance_target,
)

logger = logging.getLogger(__name__)


def _seg_field(seg: Any, key: str, default: Any = None) -> Any:
    if isinstance(seg, dict):
        return seg.get(key, default)
    return getattr(seg, key, default)


def _augment_prompt_for_chain(prompt: str) -> str:
    p = (prompt or "").strip() or " "
    tip = "【衔接】首帧承接上一镜头尾帧，动作与构图连续过渡。"
    if tip in p:
        return p
    return f"{tip}\n{p}"


def _build_content(
    prompt: str,
    image_urls: List[str],
    *,
    prev_last_frame: Optional[str],
    chaining: bool,
) -> List[Dict[str, Any]]:
    text = _augment_prompt_for_chain(prompt) if chaining else ((prompt or "").strip() or " ")
    content: List[Dict[str, Any]] = [{"type": "text", "text": text}]
    refs = list(image_urls or [])
    if chaining and prev_last_frame:
        refs = [prev_last_frame] + refs
    max_refs = 7 if chaining else 8
    for raw in refs[:max_refs]:
        u = (raw or "").strip()
        if not u:
            continue
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": u},
                "role": "reference_image",
            }
        )
    return content


async def _download_video(url: str, dest: Path) -> None:
    client = get_http_client()
    async with client.stream("GET", url, timeout=300.0, follow_redirects=True) as resp:
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            async for chunk in resp.aiter_bytes():
                f.write(chunk)


async def generate_segments(
    *,
    compile_result: Dict[str, Any],
    out_dir: Path,
    user_id: str = "local",
    user_resolution: str = "720P",
    chain_last_frame: bool = True,
    ratio: str = "9:16",
    has_face_ref: bool = False,
) -> Dict[str, Any]:
    """
    按 compile_result.segments 逐段生成。
    返回 {
      "segment_results": [...],
      "status": completed|partial_success|failed,
      "resolved_ark_model": str,
    }
    """
    segments = compile_result.get("segments") or []
    involves = bool(compile_result.get("involves_real_person"))
    text_heavy = bool(compile_result.get("product_text_heavy"))
    # 生成时重算模型（含分辨率与文字密集），避免与 CLI 不一致
    resolved = await resolve_ark_model_async(
        involves,
        bool(has_face_ref),
        user_resolution=user_resolution,
        product_text_heavy=text_heavy,
    )

    gen_res, enhance_target = resolve_gen_and_enhance_target(user_resolution)
    gen_res = normalize_user_resolution(gen_res)
    print(
        f"       路由 model={resolved} resolution={gen_res} "
        f"text_heavy={text_heavy} involves={involves} has_face={has_face_ref}"
    )
    seg_dir = Path(out_dir) / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    n = len(segments)
    prev_last: Optional[str] = None
    results: List[Dict[str, Any]] = []
    ok = 0
    fail = 0

    for i, seg in enumerate(segments):
        idx = int(_seg_field(seg, "index", i) or i)
        prompt = str(_seg_field(seg, "prompt") or "")
        task_type = str(_seg_field(seg, "task_type") or "i2v").lower()
        dur = int(float(_seg_field(seg, "duration") or 5))
        dur = max(2, min(15, dur))
        refs = list(_seg_field(seg, "reference_image_urls") or [])
        use_chain = bool(chain_last_frame) and task_type == "i2v"
        chaining = use_chain and i > 0 and bool(prev_last)
        need_last = use_chain and i < n - 1

        content = _build_content(
            prompt,
            refs,
            prev_last_frame=prev_last,
            chaining=chaining,
        )
        ark_body: Dict[str, Any] = {
            "model": resolved,
            "content": content,
            "duration": dur,
            "watermark": False,
            "generate_audio": True,
            "return_last_frame": need_last,
            "ratio": ratio or "9:16",
            "_haoya_output_resolution": gen_res,
        }

        job_id = new_job_id()
        print(f"       生成段 {i + 1}/{n} job={job_id} model={resolved} …")
        await create_job(
            job_id=job_id,
            user_id=user_id,
            duration_sec=dur,
            user_resolution=user_resolution,
            gen_resolution=gen_res,
            enhance_target=enhance_target,
            resolved_model=resolved,
            involves_real_person=involves,
            has_face_ref=has_face_ref,
            source="oneclick",
            segment_index=idx,
            request_json=ark_body,
        )
        await run_viral_job_pipeline(job_id)
        job = await get_job(job_id) or {}
        status = str(job.get("status") or "")
        video_url = (job.get("video_url_enhanced") or job.get("video_url_raw") or "").strip()
        last_frame = (job.get("last_frame_url") or "").strip() or None
        err = job.get("error_message") or ""

        entry: Dict[str, Any] = {
            "index": idx,
            "duration": dur,
            "prompt_file": f"segments/{idx + 1:03d}.json",
            "video_file": None,
            "video_url": video_url or None,
            "ark_model": resolved,
            "job_id": job_id,
            "status": "failed",
            "error": None,
        }

        if status in ("completed", "partial_success") and video_url:
            dest = seg_dir / f"{idx + 1:03d}.mp4"
            try:
                await _download_video(video_url, dest)
                entry["video_file"] = f"segments/{idx + 1:03d}.mp4"
                entry["status"] = "completed" if status == "completed" else "partial_success"
                ok += 1
                if need_last and last_frame:
                    prev_last = last_frame
                elif need_last:
                    prev_last = None
            except Exception as e:
                logger.exception("download failed seg=%s", idx)
                entry["status"] = "failed"
                entry["error"] = f"下载失败: {e}"
                entry["video_url"] = video_url
                fail += 1
                prev_last = None
        else:
            entry["error"] = err or status or "生成失败"
            fail += 1
            prev_last = None
            print(f"       段 {i + 1} 失败: {entry['error']}")

        results.append(entry)

    if fail == 0 and ok > 0:
        overall = "completed"
    elif ok > 0:
        overall = "partial_success"
    elif n == 0:
        overall = "failed"
    else:
        overall = "failed"

    return {
        "segment_results": results,
        "status": overall,
        "resolved_ark_model": resolved,
        "ok": ok,
        "fail": fail,
    }
