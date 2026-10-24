"""爆款复刻链路 Pydantic 模型。"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.services.viral_studio.llm_normalize import (
    _coerce_bool,
    _coerce_str_list,
    normalize_adapted_script,
    normalize_audio_layer,
    normalize_edit,
    normalize_global_edit,
    normalize_spatial_adapt,
    normalize_spatial_dna,
    normalize_transition_out,
    normalize_video_dna,
    normalize_visual,
)


class VideoMeta(BaseModel):
    duration_sec: float = 0
    aspect_ratio: str = "9:16"
    genre: str = ""

    @field_validator("genre", "aspect_ratio", mode="before")
    @classmethod
    def _coerce_meta_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


class VideoRhythm(BaseModel):
    avg_shot_sec: float = 0
    beat_points_sec: List[float] = Field(default_factory=list)
    pace: str = ""


class CopyFramework(BaseModel):
    structure: List[str] = Field(default_factory=list)
    hook_type: str = ""


class VoiceoverInfo(BaseModel):
    speaker: str = ""
    text: str = ""
    tone: str = ""

    @field_validator("speaker", "text", "tone", mode="before")
    @classmethod
    def _coerce_voiceover_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


class AudioLayer(BaseModel):
    voiceover: Optional[VoiceoverInfo] = None
    ambient: str = ""
    bgm: str = ""
    sfx: str = ""
    sfx_at_sec: float = 0

    @field_validator("ambient", "bgm", "sfx", mode="before")
    @classmethod
    def _coerce_audio_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("sfx_at_sec", mode="before")
    @classmethod
    def _coerce_sfx_at_sec(cls, v: Any) -> float:
        if v is None:
            return 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0


class TimelineEntry(BaseModel):
    start: float = 0
    end: float = 0
    beat_role: str = ""
    emotion: str = ""
    shot_intent: str = ""
    performance: str = ""
    product_presence: str = ""
    visual: Dict[str, Any] = Field(default_factory=dict)
    spatial: Dict[str, Any] = Field(default_factory=dict)
    audio: AudioLayer = Field(default_factory=AudioLayer)
    edit: Dict[str, Any] = Field(default_factory=dict)
    transition_out: Dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "beat_role",
        "emotion",
        "shot_intent",
        "performance",
        "product_presence",
        mode="before",
    )
    @classmethod
    def _coerce_timeline_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("spatial", mode="before")
    @classmethod
    def _coerce_spatial(cls, v: Any) -> Dict[str, Any]:
        return normalize_spatial_dna(v)

    @field_validator("edit", mode="before")
    @classmethod
    def _coerce_edit(cls, v: Any) -> Dict[str, Any]:
        return normalize_edit(v)

    @field_validator("transition_out", mode="before")
    @classmethod
    def _coerce_transition_out(cls, v: Any) -> Dict[str, Any]:
        return normalize_transition_out(v)

    @field_validator("visual", mode="before")
    @classmethod
    def _coerce_visual(cls, v: Any) -> Dict[str, Any]:
        return normalize_visual(v)

    @field_validator("audio", mode="before")
    @classmethod
    def _coerce_audio(cls, v: Any) -> Any:
        if isinstance(v, AudioLayer):
            return v
        return normalize_audio_layer(v)


class TransitionEntry(BaseModel):
    at_sec: float = 0
    type: str = ""
    on_beat: bool = False

    @field_validator("on_beat", mode="before")
    @classmethod
    def _coerce_on_beat(cls, v: Any) -> bool:
        return _coerce_bool(v)


class VideoDNA(BaseModel):
    meta: VideoMeta = Field(default_factory=VideoMeta)
    rhythm: VideoRhythm = Field(default_factory=VideoRhythm)
    copy_framework: CopyFramework = Field(default_factory=CopyFramework)
    timeline: List[TimelineEntry] = Field(default_factory=list)
    transitions: List[TransitionEntry] = Field(default_factory=list)
    global_edit: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("global_edit", mode="before")
    @classmethod
    def _coerce_global_edit(cls, v: Any) -> Dict[str, Any]:
        return normalize_global_edit(v)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VideoDNA":
        return cls.model_validate(normalize_video_dna(data))


class VoiceDeliverySix(BaseModel):
    """配音六维发声（声音/语速/呼吸/停顿/重音/尾音）。"""

    volume: str = ""
    pace: str = ""
    breath: str = ""
    pause: str = ""
    stress: str = ""
    tail: str = ""


class ShotAudio(BaseModel):
    voiceover_semantic: str = ""
    voiceover_performed: str = ""
    tone_label: str = ""
    emotion: str = ""
    delivery: VoiceDeliverySix = Field(default_factory=VoiceDeliverySix)
    delivery_prompt: str = ""
    bgm: str = ""
    ambient: str = ""
    sfx: str = ""

    @field_validator(
        "voiceover_semantic",
        "voiceover_performed",
        "tone_label",
        "emotion",
        "delivery_prompt",
        "bgm",
        "ambient",
        "sfx",
        mode="before",
    )
    @classmethod
    def _coerce_audio_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


class ShotPromptSix(BaseModel):
    """Seedance 官方六要素：主体+运动+环境+运镜/切镜+美学+音频。"""

    subject: str = ""
    motion: str = ""
    environment: str = ""
    spatial: List[str] = Field(default_factory=list)
    camera_cut: str = ""
    aesthetic: str = ""
    audio: ShotAudio = Field(default_factory=ShotAudio)

    @field_validator(
        "subject",
        "motion",
        "environment",
        "camera_cut",
        "aesthetic",
        mode="before",
    )
    @classmethod
    def _coerce_six_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("spatial", mode="before")
    @classmethod
    def _coerce_spatial_list(cls, v: Any) -> List[str]:
        return normalize_spatial_adapt(v)


class AdaptedScene(BaseModel):
    scene_id: int = 0
    time_range: str = ""
    start_sec: float = 0
    end_sec: float = 0
    beat_role: str = ""
    emotion: str = ""
    shot_intent: str = ""
    new_voiceover: str = ""
    visual_brief: str = ""
    camera: str = ""
    must_show: List[str] = Field(default_factory=list)
    continuity_from_prev: Optional[str] = None
    six: ShotPromptSix = Field(default_factory=ShotPromptSix)

    @field_validator(
        "time_range",
        "beat_role",
        "emotion",
        "shot_intent",
        "new_voiceover",
        "visual_brief",
        "camera",
        mode="before",
    )
    @classmethod
    def _coerce_optional_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("continuity_from_prev", mode="before")
    @classmethod
    def _coerce_continuity(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        return str(v)

    @field_validator("must_show", mode="before")
    @classmethod
    def _coerce_must_show(cls, v: Any) -> List[str]:
        return _coerce_str_list(v)


class ReferenceRole(BaseModel):
    """参考图角色映射（1-based index；Seedance / Happyhorse 共用）。"""

    index: int = 1
    role: Literal["product", "character", "scene", "other"] = "product"
    label: str = ""


class GlobalConsistency(BaseModel):
    character: str = ""
    product_ref: str = "参考图1"
    tone: str = ""


class InferredProduct(BaseModel):
    name: str = ""
    category: str = ""
    selling_points: List[str] = Field(default_factory=list)
    visual_traits: str = ""
    product_text_heavy: bool = False
    product_text_heavy_reason: str = ""

    @field_validator("name", "category", "visual_traits", "product_text_heavy_reason", mode="before")
    @classmethod
    def _coerce_inferred_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("selling_points", mode="before")
    @classmethod
    def _coerce_selling_points(cls, v: Any) -> List[str]:
        return _coerce_str_list(v)

    @field_validator("product_text_heavy", mode="before")
    @classmethod
    def _coerce_product_text_heavy(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        return s in ("1", "true", "yes", "y", "是")


class PresentationProfile(BaseModel):
    mode: Literal[
        "on_screen_face",
        "on_screen_hand",
        "on_screen_body",
        "off_screen",
        "none",
    ] = "none"
    display_style: str = ""
    typical_actions: List[str] = Field(default_factory=list)
    scene_type: str = ""
    generic_character: str = ""

    @field_validator("display_style", "scene_type", "generic_character", mode="before")
    @classmethod
    def _coerce_presentation_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("typical_actions", mode="before")
    @classmethod
    def _coerce_typical_actions(cls, v: Any) -> List[str]:
        return _coerce_str_list(v)


class VoiceoverSegment(BaseModel):
    """Pass B1：按 timeline 切分的口播片段（锁口播后供 B2 使用）。"""

    scene_id: int = 0
    start_sec: float = 0
    end_sec: float = 0
    text: str = ""
    voiceover_goal: str = ""

    @field_validator("text", "voiceover_goal", mode="before")
    @classmethod
    def _coerce_segment_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)


class BeatPlanEntry(BaseModel):
    scene_id: int = 0
    beat_role: str = ""
    primary_selling_point: str = ""
    display_action: str = ""
    reference_image: str = "参考图1"
    voiceover_goal: str = ""
    must_avoid: List[str] = Field(default_factory=list)

    @field_validator(
        "beat_role",
        "primary_selling_point",
        "display_action",
        "reference_image",
        "voiceover_goal",
        mode="before",
    )
    @classmethod
    def _coerce_beat_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("must_avoid", mode="before")
    @classmethod
    def _coerce_must_avoid(cls, v: Any) -> List[str]:
        return _coerce_str_list(v)


class SourceProductProfile(BaseModel):
    category: str = ""
    keywords: List[str] = Field(default_factory=list)
    selling_points_inferred: List[str] = Field(default_factory=list)

    @field_validator("category", mode="before")
    @classmethod
    def _coerce_source_cat(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("keywords", "selling_points_inferred", mode="before")
    @classmethod
    def _coerce_source_lists(cls, v: Any) -> List[str]:
        return _coerce_str_list(v)


class CoherenceReport(BaseModel):
    passed: bool = True
    category_distance: str = "unknown"
    fixes_applied: List[str] = Field(default_factory=list)
    scenes_retried: List[int] = Field(default_factory=list)
    failed_scene_ids: List[int] = Field(default_factory=list)

    @field_validator("category_distance", mode="before")
    @classmethod
    def _coerce_distance(cls, v: Any) -> str:
        if v is None:
            return "unknown"
        return str(v)

    @field_validator("fixes_applied", mode="before")
    @classmethod
    def _coerce_fixes(cls, v: Any) -> List[str]:
        return _coerce_str_list(v)

    @field_validator("scenes_retried", "failed_scene_ids", mode="before")
    @classmethod
    def _coerce_int_lists(cls, v: Any) -> List[int]:
        if v is None:
            return []
        if not isinstance(v, list):
            return []
        out: List[int] = []
        for item in v:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out


class AdaptedScript(BaseModel):
    adapted_script: List[AdaptedScene] = Field(default_factory=list)
    global_consistency: GlobalConsistency = Field(default_factory=GlobalConsistency)
    inferred_product: Optional[InferredProduct] = None
    reference_roles: List[ReferenceRole] = Field(default_factory=list)
    beat_plan: List[BeatPlanEntry] = Field(default_factory=list)
    source_product: Optional[SourceProductProfile] = None
    coherence_report: Optional[CoherenceReport] = None
    presentation_profile: Optional[PresentationProfile] = None
    full_voiceover: str = ""
    voiceover_segments: List[VoiceoverSegment] = Field(default_factory=list)

    @field_validator("full_voiceover", mode="before")
    @classmethod
    def _coerce_full_voiceover(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdaptedScript":
        return cls.model_validate(normalize_adapted_script(data))


class PlannedSegment(BaseModel):
    index: int = 0
    start_sec: float = 0
    end_sec: float = 0
    duration: float = 0


class SeedanceSegment(BaseModel):
    index: int = 0
    start_sec: float = 0
    end_sec: float = 0
    duration: float = 0
    task_type: Literal["i2v", "r2v"] = "i2v"
    reference_video_url: Optional[str] = None
    reference_image_urls: List[str] = Field(default_factory=list)
    prompt: str = ""
    voiceover: str = ""
    audio_hint: str = ""
    continuity_from_prev: Optional[str] = None
    transition_out: str = ""
    prompt_source: Literal["template", "vc", "vc_fallback"] = "template"

    @field_validator("duration")
    @classmethod
    def duration_max_15(cls, v: float) -> float:
        if v > 15.01:
            raise ValueError(f"Seedance 单段时长不能超过 15s，当前 {v}")
        return v


class CompileResult(BaseModel):
    total_duration_sec: float = 0
    segment_count: int = 0
    segments: List[SeedanceSegment] = Field(default_factory=list)
    global_consistency: GlobalConsistency = Field(default_factory=GlobalConsistency)
    voiceover_language: str = "zh"
    involves_real_person: bool = False
    person_detection_reason: str = "none"
    resolved_ark_model: str = ""
    product_text_heavy: bool = False
    product_text_heavy_reason: str = ""

    @field_validator("product_text_heavy_reason", mode="before")
    @classmethod
    def _coerce_compile_text_reason(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator("product_text_heavy", mode="before")
    @classmethod
    def _coerce_compile_text_heavy(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        return s in ("1", "true", "yes", "y", "是")


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class PipelineResult(BaseModel):
    video_dna: VideoDNA
    adapted_script: AdaptedScript
    compile_result: CompileResult
    usage: UsageInfo = Field(default_factory=UsageInfo)
    cost: int = 0
    remaining_balance: int = 0
