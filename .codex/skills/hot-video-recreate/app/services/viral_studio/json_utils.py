"""JSON 解析容错（独立于 prompt_agent）。"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


def strip_json_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def parse_json_object(raw: str) -> Dict[str, Any]:
    """从 LLM 输出解析 JSON 对象，失败时尝试提取首个 {...} 块。"""
    text = strip_json_fence(raw)
    if not text:
        raise ValueError("模型返回为空")
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    raise ValueError(f"无法解析 JSON: {text[:200]}...")
