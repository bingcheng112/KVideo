"""LLM JSON 输出归一化（Pass A/B 兼容层）。"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, Union


def _coerce_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip() if isinstance(v, str) else str(v)


def _coerce_str_list(v: Any) -> List[str]:
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, list):
        return [_coerce_str(x) for x in v if _coerce_str(x)]
    return [_coerce_str(v)] if _coerce_str(v) else []


def _coerce_float_list(v: Any) -> List[float]:
    if v is None:
        return []
    if not isinstance(v, list):
        return []
    out: List[float] = []
    for item in v:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            continue
    return out


def _coerce_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "on")
    return False


def normalize_spatial_dna(v: Any) -> Dict[str, Any]:
    """DNA timeline.spatial：期望 dict with relations。"""
    if v is None:
        return {}
    if isinstance(v, list):
        return {"relations": _coerce_str_list(v)}
    if isinstance(v, str):
        s = v.strip()
        return {"relations": [s]} if s else {}
    if isinstance(v, dict):
        out = dict(v)
        rel = out.get("relations")
        if rel is None:
            return out
        out["relations"] = _coerce_str_list(rel)
        return out
    return {}


def normalize_spatial_adapt(v: Any) -> List[str]:
    """Adapt six.spatial：期望 list[str]。"""
    if v is None:
        return []
    if isinstance(v, list):
        return _coerce_str_list(v)
    if isinstance(v, str):
        s = v.strip()
        return [s] if s else []
    if isinstance(v, dict):
        rel = v.get("relations")
        if rel is not None:
            return _coerce_str_list(rel)
        vals = [_coerce_str(x) for x in v.values() if _coerce_str(x)]
        return vals
    return []


def normalize_transition_out(v: Any) -> Dict[str, Any]:
    if v is None:
        return {}
    if isinstance(v, str):
        s = v.strip()
        return {"type": s} if s else {}
    if isinstance(v, dict):
        out = dict(v)
        if "type" in out and out["type"] is not None:
            out["type"] = _coerce_str(out["type"])
        if "on_beat" in out:
            out["on_beat"] = _coerce_bool(out["on_beat"])
        if "duration_sec" in out:
            try:
                out["duration_sec"] = float(out["duration_sec"])
            except (TypeError, ValueError):
                out["duration_sec"] = 0.0
        return out
    return {}


def normalize_edit(v: Any) -> Dict[str, Any]:
    if v is None:
        return {}
    if not isinstance(v, dict):
        return {}
    out = dict(v)
    for key in ("cut_type", "speed", "rhythm_note"):
        if key in out:
            out[key] = _coerce_str(out.get(key))
    if "transition_out" in out:
        out["transition_out"] = normalize_transition_out(out.get("transition_out"))
    return out


def normalize_global_edit(v: Any) -> Dict[str, Any]:
    if v is None:
        return {}
    if not isinstance(v, dict):
        return {}
    out = dict(v)
    for key in ("overall_pace", "dominant_transition", "color_style"):
        if key in out:
            out[key] = _coerce_str(out.get(key))
    if "has_text_overlay" in out:
        out["has_text_overlay"] = _coerce_bool(out.get("has_text_overlay"))
    return out


def resolve_transition_out(entry: Union[Dict[str, Any], None]) -> Dict[str, Any]:
    """优先 edit.transition_out，fallback timeline.transition_out。"""
    if not isinstance(entry, dict):
        return {}
    edit = entry.get("edit") or {}
    if isinstance(edit, dict):
        tr = edit.get("transition_out")
        if isinstance(tr, dict) and tr.get("type"):
            return dict(tr)
    tr_top = entry.get("transition_out")
    if isinstance(tr_top, dict):
        return dict(tr_top)
    if isinstance(tr_top, str) and tr_top.strip():
        return {"type": tr_top.strip()}
    return {}


def normalize_voiceover(v: Any) -> Optional[Dict[str, Any]]:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return {"text": s, "speaker": "", "tone": ""} if s else None
    if isinstance(v, dict):
        return {
            "speaker": _coerce_str(v.get("speaker")),
            "text": _coerce_str(v.get("text")),
            "tone": _coerce_str(v.get("tone")),
        }
    return None


def normalize_audio_layer(v: Any) -> Dict[str, Any]:
    if v is None:
        return {}
    if isinstance(v, str):
        s = v.strip()
        return {"voiceover": {"text": s}, "ambient": "", "bgm": "", "sfx": ""} if s else {}
    if not isinstance(v, dict):
        return {}
    out = dict(v)
    vo = out.get("voiceover")
    if vo is not None:
        normalized_vo = normalize_voiceover(vo)
        out["voiceover"] = normalized_vo
    for key in ("ambient", "bgm", "sfx"):
        if key in out:
            out[key] = _coerce_str(out.get(key))
    if "sfx_at_sec" in out:
        try:
            out["sfx_at_sec"] = float(out["sfx_at_sec"])
        except (TypeError, ValueError):
            out["sfx_at_sec"] = 0.0
    return out


def normalize_visual(v: Any) -> Dict[str, Any]:
    if v is None:
        return {}
    if isinstance(v, str):
        s = v.strip()
        return {"description": s} if s else {}
    if not isinstance(v, dict):
        return {}
    out = dict(v)
    tags = out.get("style_tags")
    if isinstance(tags, str):
        s = tags.strip()
        out["style_tags"] = [s] if s else []
    elif isinstance(tags, list):
        out["style_tags"] = _coerce_str_list(tags)
    subs = out.get("subjects")
    if subs is not None and not isinstance(subs, list):
        out["subjects"] = []
    for key in ("camera_motion", "color_grade"):
        if key in out:
            out[key] = _coerce_str(out.get(key))
    if "in_shot_effects" in out:
        out["in_shot_effects"] = _coerce_str_list(out.get("in_shot_effects"))
    return out


def _normalize_timeline_entry(entry: Any) -> Dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    out = dict(entry)
    for key in (
        "beat_role",
        "emotion",
        "shot_intent",
        "performance",
        "product_presence",
    ):
        if key in out:
            out[key] = _coerce_str(out.get(key))
    for key in ("start", "end"):
        if key in out:
            try:
                out[key] = float(out[key])
            except (TypeError, ValueError):
                out[key] = 0.0
    if "spatial" in out:
        out["spatial"] = normalize_spatial_dna(out.get("spatial"))
    if "edit" in out:
        out["edit"] = normalize_edit(out.get("edit"))
    if "transition_out" in out:
        out["transition_out"] = normalize_transition_out(out.get("transition_out"))
    edit = out.get("edit") or {}
    edit_tr = edit.get("transition_out") if isinstance(edit, dict) else {}
    top_tr = out.get("transition_out") or {}
    if isinstance(edit_tr, dict) and edit_tr.get("type") and not (
        isinstance(top_tr, dict) and top_tr.get("type")
    ):
        out["transition_out"] = dict(edit_tr)
    if "visual" in out:
        out["visual"] = normalize_visual(out.get("visual"))
    if "audio" in out:
        out["audio"] = normalize_audio_layer(out.get("audio"))
    return out


def _normalize_shot_six(six: Any) -> Dict[str, Any]:
    if not isinstance(six, dict):
        return {}
    out = dict(six)
    for key in ("subject", "motion", "environment", "camera_cut", "aesthetic"):
        if key in out:
            out[key] = _coerce_str(out.get(key))
    if "spatial" in out:
        out["spatial"] = normalize_spatial_adapt(out.get("spatial"))
    if "audio" in out and isinstance(out["audio"], dict):
        audio = dict(out["audio"])
        for ak in (
            "voiceover_semantic",
            "voiceover_performed",
            "tone_label",
            "emotion",
            "delivery_prompt",
            "bgm",
            "ambient",
            "sfx",
        ):
            if ak in audio:
                audio[ak] = _coerce_str(audio.get(ak))
        if "delivery" in audio and isinstance(audio["delivery"], dict):
            delivery = dict(audio["delivery"])
            for dk in ("volume", "pace", "breath", "pause", "stress", "tail"):
                if dk in delivery:
                    delivery[dk] = _coerce_str(delivery.get(dk))
            audio["delivery"] = delivery
        out["audio"] = audio
    return out


def _normalize_adapted_scene(scene: Any) -> Dict[str, Any]:
    if not isinstance(scene, dict):
        return {}
    out = dict(scene)
    for key in (
        "time_range",
        "beat_role",
        "emotion",
        "shot_intent",
        "new_voiceover",
        "visual_brief",
        "camera",
    ):
        if key in out:
            out[key] = _coerce_str(out.get(key))
    if "continuity_from_prev" in out and out["continuity_from_prev"] is not None:
        out["continuity_from_prev"] = _coerce_str(out["continuity_from_prev"])
    if "must_show" in out:
        out["must_show"] = _coerce_str_list(out.get("must_show"))
    if "six" in out:
        out["six"] = _normalize_shot_six(out.get("six"))
    for key in ("start_sec", "end_sec"):
        if key in out:
            try:
                out[key] = float(out[key])
            except (TypeError, ValueError):
                out[key] = 0.0
    if "scene_id" in out:
        try:
            out["scene_id"] = int(out["scene_id"])
        except (TypeError, ValueError):
            out["scene_id"] = 0
    return out


def normalize_video_dna(data: Union[Dict[str, Any], None]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    out = deepcopy(data)

    meta = out.get("meta")
    if isinstance(meta, dict):
        m = dict(meta)
        for key in ("genre", "aspect_ratio", "pace"):
            if key in m:
                m[key] = _coerce_str(m.get(key))
        if "duration_sec" in m:
            try:
                m["duration_sec"] = float(m["duration_sec"])
            except (TypeError, ValueError):
                m["duration_sec"] = 0.0
        out["meta"] = m

    rhythm = out.get("rhythm")
    if isinstance(rhythm, dict):
        r = dict(rhythm)
        if "beat_points_sec" in r:
            r["beat_points_sec"] = _coerce_float_list(r.get("beat_points_sec"))
        if "avg_shot_sec" in r:
            try:
                r["avg_shot_sec"] = float(r["avg_shot_sec"])
            except (TypeError, ValueError):
                r["avg_shot_sec"] = 0.0
        if "pace" in r:
            r["pace"] = _coerce_str(r.get("pace"))
        out["rhythm"] = r

    cf = out.get("copy_framework")
    if isinstance(cf, dict):
        c = dict(cf)
        if "structure" in c:
            c["structure"] = _coerce_str_list(c.get("structure"))
        if "hook_type" in c:
            c["hook_type"] = _coerce_str(c.get("hook_type"))
        out["copy_framework"] = c

    if "timeline" in out and isinstance(out["timeline"], list):
        out["timeline"] = [_normalize_timeline_entry(e) for e in out["timeline"]]

    if "transitions" in out and isinstance(out["transitions"], list):
        transitions = []
        for tr in out["transitions"]:
            if not isinstance(tr, dict):
                continue
            t = dict(tr)
            if "type" in t:
                t["type"] = _coerce_str(t.get("type"))
            if "on_beat" in t:
                t["on_beat"] = _coerce_bool(t.get("on_beat"))
            if "at_sec" in t:
                try:
                    t["at_sec"] = float(t["at_sec"])
                except (TypeError, ValueError):
                    t["at_sec"] = 0.0
            transitions.append(t)
        out["transitions"] = transitions

    if "global_edit" in out:
        out["global_edit"] = normalize_global_edit(out.get("global_edit"))

    return out


def normalize_adapted_script(data: Union[Dict[str, Any], None]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    out = deepcopy(data)

    if "adapted_script" in out and isinstance(out["adapted_script"], list):
        out["adapted_script"] = [_normalize_adapted_scene(s) for s in out["adapted_script"]]

    gc = out.get("global_consistency")
    if isinstance(gc, dict):
        g = dict(gc)
        for key in ("character", "product_ref", "tone"):
            if key in g:
                g[key] = _coerce_str(g.get(key))
        out["global_consistency"] = g

    ip = out.get("inferred_product")
    if isinstance(ip, dict):
        p = dict(ip)
        for key in ("name", "category", "visual_traits"):
            if key in p:
                p[key] = _coerce_str(p.get(key))
        if "selling_points" in p:
            p["selling_points"] = _coerce_str_list(p.get("selling_points"))
        out["inferred_product"] = p

    sp = out.get("source_product")
    if isinstance(sp, dict):
        s = dict(sp)
        if "category" in s:
            s["category"] = _coerce_str(s.get("category"))
        for key in ("keywords", "selling_points_inferred"):
            if key in s:
                s[key] = _coerce_str_list(s.get(key))
        out["source_product"] = s

    bp = out.get("beat_plan")
    if isinstance(bp, list):
        normalized_bp: List[Dict[str, Any]] = []
        for item in bp:
            if not isinstance(item, dict):
                continue
            entry = dict(item)
            try:
                entry["scene_id"] = int(entry.get("scene_id") or 0)
            except (TypeError, ValueError):
                entry["scene_id"] = 0
            for key in (
                "beat_role",
                "primary_selling_point",
                "display_action",
                "reference_image",
                "voiceover_goal",
            ):
                if key in entry:
                    entry[key] = _coerce_str(entry.get(key))
            if "must_avoid" in entry:
                entry["must_avoid"] = _coerce_str_list(entry.get("must_avoid"))
            normalized_bp.append(entry)
        out["beat_plan"] = normalized_bp

    cr = out.get("coherence_report")
    if isinstance(cr, dict):
        r = dict(cr)
        if "passed" in r:
            r["passed"] = _coerce_bool(r.get("passed"))
        if "category_distance" in r:
            r["category_distance"] = _coerce_str(r.get("category_distance"))
        if "fixes_applied" in r:
            r["fixes_applied"] = _coerce_str_list(r.get("fixes_applied"))
        for key in ("scenes_retried", "failed_scene_ids"):
            if key in r and isinstance(r[key], list):
                ints: List[int] = []
                for x in r[key]:
                    try:
                        ints.append(int(x))
                    except (TypeError, ValueError):
                        continue
                r[key] = ints
        out["coherence_report"] = r

    pp = out.get("presentation_profile")
    if isinstance(pp, dict):
        p = dict(pp)
        mode = _coerce_str(p.get("mode") or "none")
        if mode not in (
            "on_screen_face",
            "on_screen_hand",
            "on_screen_body",
            "off_screen",
            "none",
        ):
            mode = "none"
        p["mode"] = mode
        for key in ("display_style", "scene_type", "generic_character"):
            if key in p:
                p[key] = _coerce_str(p.get(key))
        if "typical_actions" in p:
            p["typical_actions"] = _coerce_str_list(p.get("typical_actions"))
        out["presentation_profile"] = p

    if "full_voiceover" in out:
        out["full_voiceover"] = _coerce_str(out.get("full_voiceover"))

    vs = out.get("voiceover_segments")
    if isinstance(vs, list):
        normalized_vs: List[Dict[str, Any]] = []
        for item in vs:
            if not isinstance(item, dict):
                continue
            seg = dict(item)
            try:
                seg["scene_id"] = int(seg.get("scene_id") or 0)
            except (TypeError, ValueError):
                seg["scene_id"] = 0
            for key in ("start_sec", "end_sec"):
                try:
                    seg[key] = float(seg.get(key) or 0)
                except (TypeError, ValueError):
                    seg[key] = 0.0
            for key in ("text", "voiceover_goal"):
                if key in seg:
                    seg[key] = _coerce_str(seg.get(key))
            normalized_vs.append(seg)
        out["voiceover_segments"] = normalized_vs

    roles = out.get("reference_roles")
    if isinstance(roles, list):
        normalized_roles: List[Dict[str, Any]] = []
        for item in roles:
            if not isinstance(item, dict):
                continue
            r = dict(item)
            try:
                r["index"] = max(1, int(r.get("index") or 1))
            except (TypeError, ValueError):
                r["index"] = 1
            role_val = _coerce_str(r.get("role") or "product").lower()
            if role_val not in ("product", "character", "scene", "other"):
                role_val = "other"
            r["role"] = role_val
            r["label"] = _coerce_str(r.get("label"))
            normalized_roles.append(r)
        out["reference_roles"] = normalized_roles

    return out
