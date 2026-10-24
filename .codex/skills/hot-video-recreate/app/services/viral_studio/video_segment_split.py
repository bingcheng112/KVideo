"""独立包 stub：R2V 切段上传（P0 默认 i2v 不调用）。"""
from __future__ import annotations

from fastapi import HTTPException, status


async def split_and_upload_segment(*args, **kwargs):
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="独立包 P0 不支持 R2V 参考视频切段；请使用 compile_strategy=i2v",
    )
