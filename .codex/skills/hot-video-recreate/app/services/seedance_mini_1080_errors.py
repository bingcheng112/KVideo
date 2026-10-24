"""Seedance mini 1080 用户可见中文错误映射。"""
from __future__ import annotations

_RETRY = "请根据提示调整后重试；若仍失败请联系客服。"


def _norm(raw: str) -> str:
    return (raw or "").strip().lower()


def map_ark_failure(raw: str) -> tuple[str, str]:
    t = _norm(raw)
    if any(k in t for k in ("face", "人脸", "portrait", "肖像")):
        msg = (
            "生成失败：参考图或视频中的人脸不符合要求（模糊、遮挡或无法识别）。"
            "请更换更清晰的正脸参考图后重试。"
        )
    elif any(k in t for k in ("safety", "审核", "risk", "违规", "content policy", "blocked")):
        msg = "生成失败：内容未通过安全审核。请修改提示词或参考素材后重试。"
    elif any(k in t for k in ("timeout", "timed out", "超时")):
        msg = "生成失败：视频生成超时。请缩短时长或稍后重试。"
    elif any(k in t for k in ("quota", "429", "rate limit", "busy", "限额")):
        msg = "生成失败：上游服务繁忙或配额不足。请稍后重试。"
    elif any(k in t for k in ("invalid", "parameter", "参数", "bad request", "400")):
        msg = "生成失败：请求参数无效。请检查分镜时长、比例与参考素材后重试。"
    elif raw and raw.strip():
        msg = f"生成失败：{raw.strip()[:200]}。请稍后重试。"
    else:
        msg = "生成失败：视频生成未成功。请稍后重试。"
    return msg, _RETRY


def map_enhance_failure(raw: str, *, gen_resolution: str = "720P") -> tuple[str, str]:
    gen = str(gen_resolution or "720P").upper()
    keep_label = "480P 成片" if gen in ("480P", "480") else "720P 成片"
    suffix = f"已为您保留 {keep_label}，仅扣除视频生成费用"
    t = _norm(raw)
    if any(k in t for k in ("403", "forbidden", "不可读", "access denied")):
        msg = f"超分失败：无法读取生成结果视频。{suffix}。"
    elif any(k in t for k in ("timeout", "超时")):
        msg = f"超分失败：画质增强处理超时。{suffix}，请稍后重试。"
    elif raw and raw.strip():
        msg = f"超分失败：{raw.strip()[:200]}。{suffix}，请稍后重试。"
    else:
        msg = f"超分失败：画质增强服务处理失败。{suffix}，请稍后重试。"
    return msg, _RETRY