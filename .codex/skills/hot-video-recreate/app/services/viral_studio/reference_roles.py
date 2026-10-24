"""参考图角色映射（Seedance / Happyhorse 共用）。"""
from __future__ import annotations

from typing import List, Optional

from app.services.viral_studio.schemas import AdaptedScript, ReferenceRole


def infer_reference_roles(
    *,
    image_count: int,
    face_ref_index: int = 0,
    product_label: str = "",
    character_label: str = "",
) -> List[ReferenceRole]:
    """规则推导 reference_roles（Pass B 未输出时的兜底）。"""
    roles: List[ReferenceRole] = []
    if image_count <= 0:
        return roles

    face_idx = int(face_ref_index or 0)
    prod_label = (product_label or "").strip() or "产品"
    char_label = (character_label or "").strip() or "出镜人物"

    if face_idx > 0 and face_idx <= image_count:
        product_indices = [i for i in range(1, image_count + 1) if i != face_idx]
        if product_indices:
            roles.append(
                ReferenceRole(index=product_indices[0], role="product", label=prod_label)
            )
        roles.append(ReferenceRole(index=face_idx, role="character", label=char_label))
        for i in range(1, image_count + 1):
            if i != face_idx and (not product_indices or i != product_indices[0]):
                label = "产品补充图" if i == 2 else f"补充参考图{i}"
                roles.append(ReferenceRole(index=i, role="other", label=label))
    else:
        roles.append(ReferenceRole(index=1, role="product", label=prod_label))
        for i in range(2, image_count + 1):
            label = "产品补充图" if i == 2 else f"补充参考图{i}"
            roles.append(ReferenceRole(index=i, role="other", label=label))
    roles.sort(key=lambda x: x.index)
    return roles


def resolve_reference_roles(
    adapted_script: Optional[AdaptedScript],
    *,
    reference_image_urls: List[str],
    face_ref_index: int = 0,
) -> List[ReferenceRole]:
    """优先读 AdaptedScript.reference_roles，否则规则推导。"""
    imgs = list(reference_image_urls or [])
    gc = adapted_script.global_consistency if adapted_script else None
    inferred = adapted_script.inferred_product if adapted_script else None
    product_label = ""
    if inferred and inferred.name:
        product_label = inferred.name
    elif inferred and inferred.visual_traits:
        product_label = inferred.visual_traits[:40]
    character_label = (gc.character if gc else "") or "出镜人物"

    if adapted_script and adapted_script.reference_roles:
        return sorted(adapted_script.reference_roles, key=lambda r: r.index)

    return infer_reference_roles(
        image_count=len(imgs),
        face_ref_index=face_ref_index,
        product_label=product_label,
        character_label=character_label[:40] if character_label else "出镜人物",
    )
