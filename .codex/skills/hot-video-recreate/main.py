#!/usr/bin/env python3
"""Seedance 一键复刻 · 独立包入口：人脸合规 → 拆解/迁移/编译 → 逐段生成。"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from io_utils import probe_video_seconds, resolve_media_ref  # noqa: E402


def _utc_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _model_to_dict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return obj
    return json.loads(json.dumps(obj, default=str))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Seedance 一键复刻：合规(可选) → 拆解→迁移→编译 → 逐段生成",
    )
    p.add_argument("--video", required=True, help="参考视频：本地路径或 http(s) URL")
    p.add_argument(
        "--image",
        action="append",
        dest="images",
        required=True,
        help="产品参考图，可重复传入",
    )
    p.add_argument("--face", default="", help="可选真人照片；默认 pencil 彩铅合规")
    p.add_argument("--product-name", default="", help="产品名称")
    p.add_argument("--product-info", default="", help="产品描述/卖点")
    p.add_argument("--out", default="./outputs", help="输出根目录")
    p.add_argument("--copy-mode", default="preserve", choices=["preserve", "rewrite"])
    p.add_argument(
        "--compile-strategy",
        default="i2v",
        choices=["i2v", "r2v", "hybrid"],
    )
    p.add_argument("--max-segment-sec", type=float, default=15.0)
    p.add_argument("--seconds", type=float, default=0, help="视频时长秒；探测失败时必填")
    p.add_argument("--voiceover-language", default="zh")
    p.add_argument("--use-vc-refine", action="store_true")
    p.add_argument(
        "--resolution",
        default="720P",
        choices=["480P", "720P", "1080P", "4K"],
        help="生成分辨率：480P/720P 可用 mini/fast/2.0；1080P/4K 仅 2.0",
    )
    p.add_argument(
        "--chain-last-frame",
        dest="chain_last_frame",
        action="store_true",
        default=True,
        help="段间尾帧链（默认开启）",
    )
    p.add_argument(
        "--no-chain-last-frame",
        dest="chain_last_frame",
        action="store_false",
        help="关闭尾帧链",
    )
    p.add_argument(
        "--skip-generate",
        action="store_true",
        default=False,
        help="只编译不生成视频",
    )
    p.add_argument(
        "--skip-face-compliance",
        action="store_true",
        default=False,
        help="有 --face 时跳过彩铅合规（调试用）",
    )
    p.add_argument("--user-id", default="local")
    return p.parse_args(argv)


async def run(args: argparse.Namespace) -> Path:
    dash_key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
    if not dash_key:
        raise SystemExit("缺少 DASHSCOPE_API_KEY，请复制 .env.example 为 .env 并填写")

    need_ark = (not args.skip_generate) or (
        bool((args.face or "").strip()) and not args.skip_face_compliance
    )
    ark_key = (os.environ.get("VOLC_ARK_API_KEY") or "").strip()
    if need_ark and not ark_key:
        raise SystemExit(
            "缺少 VOLC_ARK_API_KEY（人脸合规 / Seedance 生成需要），请写入 .env"
        )

    from app.core.http_client import close_http_client, init_http_client
    from app.services.viral_studio.orchestrator import run_full_pipeline
    from generate_batch import generate_segments

    init_http_client()
    run_id = _utc_run_id()
    out_root = Path(args.out).resolve()
    out_dir = out_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    seg_dir = out_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    face_meta: Dict[str, Any] = {"enabled": False}

    try:
        print("[1/5] 规范化输入…")
        video_url = resolve_media_ref(args.video, kind="video")
        image_urls = [resolve_media_ref(img, kind="image") for img in (args.images or [])]
        if not image_urls:
            raise SystemExit("至少需要一张 --image 产品图")

        face_ref_index = 0
        face_raw = (args.face or "").strip()
        if face_raw:
            face_src = resolve_media_ref(face_raw, kind="image")
            if args.skip_face_compliance:
                print("       跳过人脸合规，直传原图")
                image_urls.append(face_src)
                face_ref_index = len(image_urls)
                face_meta = {
                    "enabled": True,
                    "mode": "raw",
                    "source": face_raw,
                    "compliant_url": face_src[:120] + ("…" if len(face_src) > 120 else ""),
                }
            else:
                print("[2/5] 人脸合规 pencil（Seedream 彩铅）…")
                from app.services.face_compliance.service import run_face_compliance

                _prompt, urls = await run_face_compliance(
                    ark_key,
                    face_src,
                    mode="pencil",
                )
                if not urls:
                    raise SystemExit("人脸合规未返回图片")
                compliant = urls[0]
                (out_dir / "face_compliant.url.txt").write_text(compliant, encoding="utf-8")
                image_urls.append(compliant)
                face_ref_index = len(image_urls)
                face_meta = {
                    "enabled": True,
                    "mode": "pencil",
                    "source": face_raw,
                    "compliant_url": compliant,
                }
                print(f"       合规图: {compliant[:100]}…")
        else:
            print("[2/5] 无人脸参考，跳过合规")

        seconds = float(args.seconds or 0)
        if seconds <= 0:
            probed = probe_video_seconds(args.video)
            if probed and probed > 0:
                seconds = probed
                print(f"       探测时长: {seconds:.1f}s")
            else:
                raise SystemExit(
                    "无法探测视频时长，请用 --seconds N 指定（整数秒，向上取整亦可）"
                )
        video_seconds = max(1, int(round(seconds)))

        print("[3/5] 流水线 deconstruct → adapt → compile…")
        print("       （可能需要数分钟，请勿中断）")
        result = await run_full_pipeline(
            str(args.user_id),
            reference_video_url=video_url,
            reference_video_seconds=video_seconds,
            product_name=(args.product_name or "").strip(),
            product_info=(args.product_info or "").strip(),
            reference_image_urls=image_urls,
            copy_mode=args.copy_mode,
            face_ref_index=face_ref_index,
            face_ref_mode="pencil",
            compile_strategy=args.compile_strategy,
            max_segment_sec=float(args.max_segment_sec),
            use_vc_refine=bool(args.use_vc_refine),
            voiceover_language=args.voiceover_language or "zh",
            user_resolution=args.resolution,
        )

        print("[4/5] 写入编译产物…")
        dna = _model_to_dict(result.video_dna)
        script = _model_to_dict(result.adapted_script)
        compile_result = _model_to_dict(result.compile_result)
        usage = _model_to_dict(result.usage)

        _write_json(out_dir / "video_dna.json", dna)
        _write_json(out_dir / "adapted_script.json", script)
        _write_json(out_dir / "compile_result.json", compile_result)

        segments = compile_result.get("segments") or []
        manifest_segments: List[Dict[str, Any]] = []
        for i, seg in enumerate(segments):
            idx = int(seg.get("index") if isinstance(seg, dict) else i)
            name = f"{idx + 1:03d}.json"
            _write_json(seg_dir / name, seg if isinstance(seg, dict) else _model_to_dict(seg))
            duration = seg.get("duration") if isinstance(seg, dict) else 0
            manifest_segments.append(
                {
                    "index": idx,
                    "duration": duration,
                    "prompt_file": f"segments/{name}",
                    "video_file": None,
                    "video_url": None,
                    "ark_model": None,
                    "job_id": None,
                    "status": "compiled",
                }
            )

        overall_status = "compiled"
        resolved_model = compile_result.get("resolved_ark_model") or ""
        text_heavy = bool(compile_result.get("product_text_heavy"))
        text_reason = compile_result.get("product_text_heavy_reason") or ""

        if not args.skip_generate:
            print("[5/5] 逐段 Seedance 生成…")
            gen = await generate_segments(
                compile_result=compile_result,
                out_dir=out_dir,
                user_id=str(args.user_id),
                user_resolution=args.resolution,
                chain_last_frame=bool(args.chain_last_frame),
                has_face_ref=face_ref_index > 0,
            )
            overall_status = gen["status"]
            resolved_model = gen.get("resolved_ark_model") or resolved_model
            by_idx = {r["index"]: r for r in gen.get("segment_results") or []}
            merged: List[Dict[str, Any]] = []
            for m in manifest_segments:
                r = by_idx.get(m["index"])
                if r:
                    merged.append({**m, **r})
                else:
                    merged.append(m)
            manifest_segments = merged
        else:
            print("[5/5] 已跳过生成（--skip-generate）")

        from app.services.seedance_viral_routing import normalize_user_resolution

        gen_resolution = normalize_user_resolution(args.resolution)

        manifest = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "video": args.video,
                "images": list(args.images or []),
                "face": face_raw or None,
                "product_name": args.product_name or "",
                "product_info": args.product_info or "",
            },
            "options": {
                "copy_mode": args.copy_mode,
                "compile_strategy": args.compile_strategy,
                "max_segment_sec": args.max_segment_sec,
                "skip_generate": bool(args.skip_generate),
                "skip_face_compliance": bool(args.skip_face_compliance),
                "resolution": args.resolution,
                "gen_resolution": gen_resolution,
                "chain_last_frame": bool(args.chain_last_frame),
                "voiceover_language": args.voiceover_language,
                "use_vc_refine": bool(args.use_vc_refine),
                "video_seconds": video_seconds,
                "face_ref_index": face_ref_index,
            },
            "face_compliance": face_meta,
            "product_text_heavy": text_heavy,
            "product_text_heavy_reason": text_reason,
            "usage": usage,
            "cost": int(getattr(result, "cost", 0) or 0),
            "segments": manifest_segments,
            "status": overall_status,
            "resolved_ark_model": resolved_model,
            "involves_real_person": bool(compile_result.get("involves_real_person")),
        }
        _write_json(out_dir / "manifest.json", manifest)

        print("完成")
        print(f"       状态: {overall_status}")
        print(f"       段数: {len(manifest_segments)}")
        print(f"       模型: {resolved_model or '-'}")
        print(f"       目录: {out_dir}")
        print(f"       manifest: {out_dir / 'manifest.json'}")
        return out_dir
    finally:
        await close_http_client()


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv(_ROOT / ".env")
    args = parse_args(argv)
    try:
        asyncio.run(run(args))
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130
    except Exception as e:
        msg = getattr(e, "detail", None) or str(e)
        print(f"失败: {msg}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
