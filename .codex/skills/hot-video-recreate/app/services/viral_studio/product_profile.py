"""原片产品画像：从 VideoDNA 提取品类/禁用词，供迁移清洗与品类距离判断。"""
from __future__ import annotations

import re
from typing import List, Literal, Optional, Set

from app.services.viral_studio.schemas import InferredProduct, SourceProductProfile, VideoDNA

CategoryDistance = Literal["near", "far", "unknown"]

# 常见品类词（用于从文本推断原片品类）
_CATEGORY_HINTS = (
    "运动鞋", "跑鞋", "休闲鞋", "篮球鞋", "板鞋", "高跟鞋", "拖鞋", "凉鞋",
    "鞋", "内衣", "文胸", "内裤", "面膜", "榨汁杯", "卫衣", "T恤", "裤子",
    "包包", "手表", "耳机", "手机壳", "护肤品", "口红", "粉底",
)

# 品类部位/动作专有词（跨品类迁移须清除）
_CATEGORY_ACTION_TERMS = (
    "鞋头", "鞋面", "鞋底", "鞋带", "上脚", "脚感", "缓震", "抓地",
    "杯型", "聚拢", "无钢圈", "面料", "垂坠", "系鞋带", "穿鞋", "脱鞋",
    "新鞋", "旧鞋", "跑鞋", "球鞋",
)

_BRAND_RE = re.compile(r"\b[A-Z][A-Z0-9]{2,}(?:\s+[A-Z][A-Z0-9]{2,})*\b")


def _collect_dna_texts(video_dna: VideoDNA) -> List[str]:
    parts: List[str] = []
    for entry in video_dna.timeline or []:
        if entry.product_presence:
            parts.append(entry.product_presence.strip())
        if entry.performance:
            parts.append(entry.performance.strip())
        if entry.shot_intent:
            parts.append(entry.shot_intent.strip())
        audio = entry.audio
        if audio and audio.voiceover and audio.voiceover.text:
            parts.append(audio.voiceover.text.strip())
        vis = entry.visual or {}
        for subj in vis.get("subjects") or []:
            if isinstance(subj, dict):
                if subj.get("desc"):
                    parts.append(str(subj["desc"]).strip())
                if subj.get("action"):
                    parts.append(str(subj["action"]).strip())
        spatial = entry.spatial or {}
        if isinstance(spatial, dict):
            for rel in spatial.get("relations") or []:
                if rel:
                    parts.append(str(rel).strip())
        elif isinstance(spatial, list):
            for rel in spatial:
                if rel:
                    parts.append(str(rel).strip())
    return [p for p in parts if p]


def _extract_brands(texts: List[str]) -> List[str]:
    found: Set[str] = set()
    for text in texts:
        for m in _BRAND_RE.finditer(text):
            brand = m.group(0).strip()
            if len(brand) >= 3:
                found.add(brand)
    return sorted(found, key=len, reverse=True)


def _infer_category_from_texts(texts: List[str]) -> str:
    blob = " ".join(texts)
    matched: List[str] = []
    for hint in _CATEGORY_HINTS:
        if hint in blob:
            matched.append(hint)
    if not matched:
        return ""
    return max(matched, key=len)


def _extract_action_terms(texts: List[str]) -> List[str]:
    blob = " ".join(texts)
    found: List[str] = []
    for term in _CATEGORY_ACTION_TERMS:
        if term in blob and term not in found:
            found.append(term)
    return found


def extract_source_product_profile(video_dna: VideoDNA) -> SourceProductProfile:
    """从 DNA 聚合原片产品关键词与推断品类。"""
    texts = _collect_dna_texts(video_dna)
    brands = _extract_brands(texts)
    category = _infer_category_from_texts(texts)
    action_terms = _extract_action_terms(texts)

    keywords: List[str] = []
    for item in brands + action_terms:
        if item and item not in keywords:
            keywords.append(item)

    # 从 product_presence 提取短词
    for entry in video_dna.timeline or []:
        pp = (entry.product_presence or "").strip()
        if pp and len(pp) <= 20 and pp not in keywords:
            keywords.append(pp)

    selling_points: List[str] = []
    for entry in video_dna.timeline or []:
        vo = ""
        if entry.audio and entry.audio.voiceover:
            vo = (entry.audio.voiceover.text or "").strip()
        if vo and len(vo) <= 40 and vo not in selling_points:
            selling_points.append(vo[:40])

    return SourceProductProfile(
        category=category,
        keywords=keywords[:30],
        selling_points_inferred=selling_points[:5],
    )


def collect_forbidden_terms(source: SourceProductProfile) -> List[str]:
    """供清洗使用的禁用词列表（长词优先）。"""
    terms: List[str] = []
    if source.category:
        terms.append(source.category)
    for kw in source.keywords or []:
        if kw and kw not in terms:
            terms.append(kw)
    return sorted(terms, key=len, reverse=True)


def _normalize_category(cat: str) -> str:
    return (cat or "").strip().lower()


def infer_category_distance(
    source: SourceProductProfile,
    target: Optional[InferredProduct],
) -> CategoryDistance:
    src = _normalize_category(source.category)
    tgt = _normalize_category(target.category if target else "")
    if not src or not tgt:
        return "unknown"
    if src == tgt:
        return "near"
    if src in tgt or tgt in src:
        return "near"
    # 同属「鞋」类等包含关系
    for hint in _CATEGORY_HINTS:
        if hint in src and hint in tgt:
            return "near"
    return "far"
