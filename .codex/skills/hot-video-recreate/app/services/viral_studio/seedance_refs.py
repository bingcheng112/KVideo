"""Seedance 参考图文案声明（参考图N 指代）。"""
from __future__ import annotations

from typing import List

from app.services.viral_studio.schemas import ReferenceRole

_ROLE_DECL_SEEDANCE = {
    "product": "主产品",
    "character": "出镜人物",
    "scene": "场景",
    "other": "补充参考",
}


def _role_phrase(role: ReferenceRole) -> str:
    label = (role.label or "").strip()
    suffix = _ROLE_DECL_SEEDANCE.get(role.role, "参考")
    if label:
        if suffix in label or role.role == "product":
            return label
        return f"{label}{suffix}"
    return suffix


def build_seedance_reference_declaration(roles: List[ReferenceRole]) -> str:
    """多图时生成参考图声明句（不含【视觉锚点】前缀）。"""
    if not roles:
        return ""
    product_and_other = [
        r for r in sorted(roles, key=lambda x: x.index) if r.role in ("product", "other", "scene")
    ]
    if len(product_and_other) <= 1:
        return ""
    parts: List[str] = []
    for r in product_and_other:
        phrase = _role_phrase(r)
        if r.role == "product":
            parts.append(f"参考图{r.index}为{phrase}")
        elif r.index == 2 and "补充" not in phrase:
            parts.append(f"参考图{r.index}为{phrase}补充")
        else:
            parts.append(f"参考图{r.index}为{phrase}")
    return "，".join(parts) + "。"


def primary_product_ref(roles: List[ReferenceRole]) -> str:
    for r in roles:
        if r.role == "product":
            return f"参考图{r.index}"
    return "参考图1"


def product_constraint_ref(roles: List[ReferenceRole]) -> str:
    """R2V 约束行用的商品替换指代。"""
    product_and_other = [
        r for r in sorted(roles, key=lambda x: x.index) if r.role in ("product", "other")
    ]
    if len(product_and_other) <= 1:
        return primary_product_ref(roles)
    main = primary_product_ref(roles)
    extras = [
        f"参考图{r.index}（{'补充' if r.role == 'other' else '主'}）"
        for r in product_and_other
        if r.role != "product"
    ]
    if not extras:
        return main
    return f"{main}及{'、'.join(extras)}"
