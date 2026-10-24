"""独立包：Seedance 模型与分辨率路由（无 DB，走 fallback）。"""
from __future__ import annotations

from typing import List, Literal, Optional, Tuple

EnhanceTarget = Literal["noop"]
GenResolution = Literal["480P", "720P", "1080P", "4K"]

_FALLBACK_MINI = "doubao-seedance-2-0-mini-260128"
_FALLBACK_FAST = "doubao-seedance-2-0-fast-260128"
_FALLBACK_STANDARD = "doubao-seedance-2-0-260128"

_HIGH_RES = frozenset({"1080P", "1080", "4K", "2160P"})


def normalize_user_resolution(user_resolution: str) -> GenResolution:
    r = str(user_resolution or "720P").upper().strip().replace(" ", "")
    if r in ("4K", "2160P", "2160"):
        return "4K"
    if r in ("1080P", "1080"):
        return "1080P"
    if r in ("480P", "480"):
        return "480P"
    return "720P"


def resolve_gen_and_enhance_target(user_resolution: str) -> Tuple[GenResolution, EnhanceTarget]:
    """用户选什么分辨率就生成什么；超分 noop。"""
    return normalize_user_resolution(user_resolution), "noop"


def requires_standard_model(
    *,
    user_resolution: str = "720P",
    product_text_heavy: bool = False,
) -> bool:
    res = normalize_user_resolution(user_resolution)
    if res in ("1080P", "4K"):
        return True
    return bool(product_text_heavy)


def resolve_ark_model_from_rows(
    involves_real_person: bool,
    has_face_ref: bool,
    model_rows: Optional[List[dict]] = None,
    *,
    user_resolution: str = "720P",
    product_text_heavy: bool = False,
) -> str:
    _ = model_rows
    if requires_standard_model(
        user_resolution=user_resolution,
        product_text_heavy=product_text_heavy,
    ):
        return _FALLBACK_STANDARD
    if not involves_real_person:
        return _FALLBACK_MINI
    if has_face_ref:
        return _FALLBACK_STANDARD
    return _FALLBACK_FAST


async def fetch_seedance_video_models() -> List[dict]:
    return []


async def resolve_ark_model_async(
    involves_real_person: bool,
    has_face_ref: bool,
    *,
    user_resolution: str = "720P",
    product_text_heavy: bool = False,
) -> str:
    return resolve_ark_model_from_rows(
        involves_real_person,
        has_face_ref,
        [],
        user_resolution=user_resolution,
        product_text_heavy=product_text_heavy,
    )
