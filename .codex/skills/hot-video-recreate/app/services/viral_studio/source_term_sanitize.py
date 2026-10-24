"""迁移脚本：清除原片品类/品牌残留词。"""
from __future__ import annotations

import re
from typing import List, Optional

from app.services.viral_studio.schemas import AdaptedScene, AdaptedScript, InferredProduct, ShotPromptSix

# 跨品类动作矛盾：口播含左列时，六要素不应含右列
_MOTION_CONFLICTS = (
    (("上脚", "鞋头", "鞋带", "鞋底", "穿鞋"), ("杯型", "面料", "内衣", "衣架")),
    (("杯型", "聚拢", "无钢圈"), ("鞋头", "上脚", "鞋带")),
)

# 跨品类视觉/动作残留（左→右替换）
_CROSS_CATEGORY_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("一双", "一件"),
    ("两双", "两件"),
    ("上脚", "穿着"),
    ("鞋头", "杯面"),
    ("鞋带", "肩带"),
    ("鞋底", "面料"),
    ("穿鞋", "穿着"),
    ("上脚感", "穿着感"),
)

# 跨品类产品名词（长词优先）
_SHOE_PRODUCT_TERMS: tuple[str, ...] = (
    "运动鞋",
    "帆布鞋",
    "高跟鞋",
    "板鞋",
    "跑鞋",
    "球鞋",
    "凉鞋",
    "拖鞋",
    "鞋子",
    "鞋",
)


def _product_display_name(target: Optional[InferredProduct]) -> str:
    if not target:
        return "参考图1产品"
    name = (target.name or "").strip()
    if name:
        return name
    category = (target.category or "").strip()
    if category:
        return category
    return "参考图1产品"


def _is_non_shoe_category(target: Optional[InferredProduct]) -> bool:
    category = (target.category if target else "") or ""
    name = (target.name if target else "") or ""
    blob = f"{category}{name}"
    return bool(blob) and "鞋" not in blob


def _replacement_for_term(term: str, target: Optional[InferredProduct]) -> str:
    if not target:
        return ""
    name = (target.name or "").strip()
    category = (target.category or "").strip()
    points = list(target.selling_points or [])
    if "鞋" in term or "脚" in term:
        if points:
            return points[0]
        if category:
            return category
        if name:
            return name
    if name:
        return name
    if category:
        return category
    if points:
        return points[0]
    return "参考图1产品"


def strip_source_terms(
    text: str,
    forbidden_terms: List[str],
    *,
    target: Optional[InferredProduct] = None,
    replacement_hint: str = "",
) -> str:
    """从文本中移除或替换原片禁用词。"""
    result = (text or "").strip()
    if not result or not forbidden_terms:
        return result

    hint = (replacement_hint or "").strip()
    for term in forbidden_terms:
        if not term or term not in result:
            continue
        repl = hint or _replacement_for_term(term, target)
        if repl and repl != term:
            result = result.replace(term, repl, 1)
        else:
            result = result.replace(term, "", 1)

    result = re.sub(r"\s{2,}", " ", result)
    result = re.sub(r"[，,]{2,}", "，", result)
    return result.strip()


def _sanitize_six_fields(
    six: ShotPromptSix,
    forbidden_terms: List[str],
    target: Optional[InferredProduct],
) -> List[str]:
    fixes: List[str] = []
    if six.subject:
        new = strip_source_terms(six.subject, forbidden_terms, target=target)
        new = fix_cross_category_visual(new, target)
        if new != six.subject:
            fixes.append(f"subject: {six.subject[:20]}…")
            six.subject = new
    if six.motion:
        new = strip_source_terms(six.motion, forbidden_terms, target=target)
        new = fix_cross_category_visual(new, target)
        if new != six.motion:
            fixes.append(f"motion: {six.motion[:20]}…")
            six.motion = new
    if six.environment:
        new = strip_source_terms(six.environment, forbidden_terms, target=target)
        if new != six.environment:
            fixes.append(f"environment: {six.environment[:20]}…")
            six.environment = new
    cleaned_spatial: List[str] = []
    for s in six.spatial or []:
        new = strip_source_terms(s, forbidden_terms, target=target)
        new = fix_cross_category_visual(new, target)
        if new:
            cleaned_spatial.append(new)
        elif s:
            fixes.append(f"spatial removed: {s[:20]}…")
    six.spatial = cleaned_spatial

    audio = six.audio
    for field in ("voiceover_semantic", "voiceover_performed", "delivery_prompt"):
        val = getattr(audio, field, "") or ""
        if val:
            new = strip_source_terms(val, forbidden_terms, target=target)
            if new != val:
                fixes.append(f"audio.{field}")
                setattr(audio, field, new)
    return fixes


def sanitize_scene_content(
    scene: AdaptedScene,
    forbidden_terms: List[str],
    target: Optional[InferredProduct] = None,
) -> List[str]:
    """就地清洗单镜内容，返回 applied fixes 描述。"""
    fixes: List[str] = []
    if scene.new_voiceover:
        new = strip_source_terms(scene.new_voiceover, forbidden_terms, target=target)
        new = fix_cross_category_visual(new, target)
        if new != scene.new_voiceover:
            fixes.append(f"scene_{scene.scene_id}: voiceover")
            scene.new_voiceover = new
    if scene.shot_intent:
        new = strip_source_terms(scene.shot_intent, forbidden_terms, target=target)
        new = fix_cross_category_visual(new, target)
        if new != scene.shot_intent:
            fixes.append(f"scene_{scene.scene_id}: shot_intent")
            scene.shot_intent = new
    if scene.visual_brief:
        new = strip_source_terms(scene.visual_brief, forbidden_terms, target=target)
        if new != scene.visual_brief:
            scene.visual_brief = new

    cleaned_must: List[str] = []
    for item in scene.must_show or []:
        new = strip_source_terms(item, forbidden_terms, target=target)
        if new:
            cleaned_must.append(new)
    scene.must_show = cleaned_must

    if scene.six:
        fixes.extend(_sanitize_six_fields(scene.six, forbidden_terms, target))

    return fixes


def fix_cross_category_visual(
    text: str,
    target: Optional[InferredProduct] = None,
) -> str:
    """清除跨品类量词/动作/产品名词残留（如鞋类词出现在内衣脚本）。"""
    result = (text or "").strip()
    if not result:
        return result
    is_non_shoe = _is_non_shoe_category(target)
    for src, dst in _CROSS_CATEGORY_REPLACEMENTS:
        if src not in result:
            continue
        if is_non_shoe or src in ("一双", "两双", "上脚", "鞋头", "鞋带", "鞋底", "穿鞋", "上脚感"):
            result = result.replace(src, dst)
    if is_non_shoe:
        product_label = _product_display_name(target)
        for term in _SHOE_PRODUCT_TERMS:
            if term in result:
                result = result.replace(term, product_label)
    result = re.sub(r"\s{2,}", " ", result)
    return result.strip()


def apply_cross_category_to_script(script: AdaptedScript) -> AdaptedScript:
    """全脚本跨品类视觉/产品名词清洗（compile 兜底，无 forbidden_terms 时仍生效）。"""
    target = script.inferred_product
    for scene in script.adapted_script or []:
        if scene.new_voiceover:
            scene.new_voiceover = fix_cross_category_visual(scene.new_voiceover, target)
        if scene.shot_intent:
            scene.shot_intent = fix_cross_category_visual(scene.shot_intent, target)
        if scene.visual_brief:
            scene.visual_brief = fix_cross_category_visual(scene.visual_brief, target)
        scene.must_show = [
            fix_cross_category_visual(item, target)
            for item in (scene.must_show or [])
            if fix_cross_category_visual(item, target)
        ]
        if not scene.six:
            continue
        six = scene.six
        for field in ("subject", "motion", "environment"):
            val = getattr(six, field, "") or ""
            if val:
                setattr(six, field, fix_cross_category_visual(val, target))
        six.spatial = [
            fix_cross_category_visual(s, target)
            for s in (six.spatial or [])
            if fix_cross_category_visual(s, target)
        ]
        audio = six.audio
        for field in ("voiceover_semantic", "voiceover_performed", "delivery_prompt"):
            val = getattr(audio, field, "") or ""
            if val:
                setattr(audio, field, fix_cross_category_visual(val, target))
    return script


def contains_forbidden(text: str, forbidden_terms: List[str]) -> List[str]:
    """返回文本中命中的禁用词。"""
    t = (text or "").strip()
    if not t:
        return []
    return [term for term in forbidden_terms if term and term in t]


def has_motion_conflict(voiceover: str, visual_text: str) -> bool:
    """口播与画面是否存在品类动作矛盾。"""
    vo = (voiceover or "").strip()
    vis = (visual_text or "").strip()
    if not vo or not vis:
        return False
    for vo_terms, vis_terms in _MOTION_CONFLICTS:
        vo_hit = any(t in vo for t in vo_terms)
        vis_hit = any(t in vis for t in vis_terms)
        if vo_hit and vis_hit:
            return True
        vo_hit2 = any(t in vo for t in vis_terms)
        vis_hit2 = any(t in vis for t in vo_terms)
        if vo_hit2 and vis_hit2:
            return True
    return False
