"""配音真实感规则（内化自 KOC 带货场景常用情绪模板）。"""
from __future__ import annotations

import re
from typing import Dict, List

from app.services.viral_studio.content_profile import VoiceoverMode
from app.services.viral_studio.voiceover_languages import is_non_chinese_voiceover

# Pass A 带货情绪 → 内部预设键
KOC_EMOTION_MAP: Dict[str, str] = {
    "好奇": "thinking",
    "焦虑": "nervous",
    "兴奋安利": "excited",
    "兴奋": "excited",
    "信任": "comfort",
    "紧迫感": "warning",
    "惊喜": "excited",
    "平淡": "calm",
    "陈述": "calm",
}

EMOTION_DELIVERY_PRESETS: Dict[str, Dict[str, str]] = {
    "thinking": {
        "volume": "语速放慢",
        "pace": "像边想边说",
        "breath": "自然呼吸",
        "pause": "关键词前逗号微顿",
        "stress": "思考词轻读",
        "tail": "尾音平稳",
        "short_template": "语速慢下来，带思考感，像边想边说：【{performed}】",
    },
    "excited": {
        "volume": "声音变亮",
        "pace": "语速稍微变快",
        "breath": "呼吸轻快",
        "pause": "卖点词前逗号微顿",
        "stress": "产品卖点词加重",
        "tail": "尾音自然上扬，带笑意",
        "short_template": "声音变亮，语速稍微变快，尾音上扬，带着真实笑意地说：【{performed}】",
    },
    "comfort": {
        "volume": "声音放轻",
        "pace": "语速慢下来",
        "breath": "气息平稳",
        "pause": "前半句柔，后半句稳",
        "stress": "安抚词轻读，承诺词稳读",
        "tail": "尾音稳稳落下",
        "short_template": "声音放轻，语速慢下来，尾音稳稳落下，像朋友真诚分享地说：【{performed}】",
    },
    "nervous": {
        "volume": "声音放轻",
        "pace": "语速慢下来",
        "breath": "呼吸变浅",
        "pause": "省略号情绪卡顿",
        "stress": "前半句轻读",
        "tail": "尾音发虚",
        "short_template": "声音放轻，呼吸变浅，语速慢下来，中间停顿明显地说：【{performed}】",
    },
    "warning": {
        "volume": "声音压低",
        "pace": "语速略快",
        "breath": "呼吸略紧",
        "pause": "逗号短停顿",
        "stress": "后半句加重",
        "tail": "尾音不要软掉",
        "short_template": "声音压低，语速略快，后半句加重，带紧迫感地说：【{performed}】",
    },
    "calm": {
        "volume": "声音平稳",
        "pace": "语速适中",
        "breath": "自然呼吸",
        "pause": "句号收住",
        "stress": "均匀陈述",
        "tail": "尾音平稳落地",
        "short_template": "声音平稳，语速适中，尾音收住，自然陈述地说：【{performed}】",
    },
}

EMOTION_DELIVERY_PRESETS_EN: Dict[str, Dict[str, str]] = {
    "thinking": {
        "volume": "voice slows down",
        "pace": "thinking out loud",
        "pause": "brief pause before key words",
        "stress": "soft stress on reflective words",
        "tail": "steady ending",
    },
    "excited": {
        "volume": "voice brightens",
        "pace": "slightly faster pace",
        "pause": "micro-pause before selling points",
        "stress": "emphasis on product benefits",
        "tail": "upbeat ending with a smile",
    },
    "comfort": {
        "volume": "voice softens",
        "pace": "slower reassuring pace",
        "pause": "gentle first half, steady second half",
        "stress": "soft reassurance, firm promise",
        "tail": "warm settled ending",
    },
    "nervous": {
        "volume": "voice lowers",
        "pace": "slower hesitant pace",
        "pause": "noticeable emotional pause",
        "stress": "lighter first half",
        "tail": "uneasy trailing ending",
    },
    "warning": {
        "volume": "voice drops",
        "pace": "slightly urgent pace",
        "pause": "short comma pauses",
        "stress": "heavier second half",
        "tail": "firm ending without softening",
    },
    "calm": {
        "volume": "steady voice",
        "pace": "moderate natural pace",
        "pause": "clean sentence endings",
        "stress": "even conversational delivery",
        "tail": "grounded ending",
    },
}


def resolve_emotion_key(emotion: str) -> str:
    emo = (emotion or "").strip()
    if emo in KOC_EMOTION_MAP:
        return KOC_EMOTION_MAP[emo]
    for k, v in KOC_EMOTION_MAP.items():
        if k in emo:
            return v
    return "calm"


def normalize_semantic(text: str) -> str:
    """去标点空白后比对语义。"""
    t = (text or "").strip()
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"[，。！？、；：…〜～—\-\"'「」【】!?.,;:'\"]+", "", t)
    return t


def _split_clauses(text: str) -> List[str]:
    """按语义块粗分（无标点时长句）。"""
    t = (text or "").strip()
    if not t:
        return []
    if re.search(r"[，。！？、；…]", t):
        return [c.strip() for c in re.split(r"(?<=[，。！？、；])|(?=…)", t) if c.strip()]
    # 无标点：每 8-12 字插逗号
    if len(t) <= 12:
        return [t]
    chunks: List[str] = []
    i = 0
    while i < len(t):
        end = min(i + 10, len(t))
        chunks.append(t[i:end])
        i = end
    return chunks


def apply_symbol_punctuation(semantic: str, emotion: str) -> str:
    """
    规则排版：semantic → performed。
    金句 case 硬编码 + 情绪通用规则。
    """
    s = (semantic or "").strip()
    if not s:
        return ""

    # PDF 金句硬编码回归
    hardcoded: Dict[str, str] = {
        "等一下我想先确认一件事": "等一下，我想，先确认一件事。",
        "别碰我的东西听懂了吗": "别碰我的东西，听懂了吗！",
        "你刚才去哪了": "你刚才……去哪了？",
    }
    norm = normalize_semantic(s)
    for k, v in hardcoded.items():
        if normalize_semantic(k) == norm:
            return v

    key = resolve_emotion_key(emotion)
    clauses = _split_clauses(s)
    if not clauses:
        return s

    if key == "thinking":
        parts = []
        for i, c in enumerate(clauses):
            c = c.rstrip("，。！？")
            if i < len(clauses) - 1:
                parts.append(c + "，")
            else:
                parts.append(c + "。")
        return "".join(parts)

    if key == "excited":
        out = []
        for i, c in enumerate(clauses):
            c = c.rstrip("，。！？")
            if i == 0 and len(clauses) > 1:
                out.append(c + "，")
            elif i == len(clauses) - 1:
                if "太好了" in c or "成功" in c:
                    out.append(c.rstrip("！") + "〜" if "〜" not in c else c)
                    if not out[-1].endswith("！") and not out[-1].endswith("。"):
                        out[-1] += "！"
                else:
                    out.append(c + ("！" if "！" not in c and "!" not in c else ""))
            else:
                out.append(c + "，")
        return "".join(out)

    if key == "nervous" or key == "warning":
        if len(clauses) == 1 and len(s) > 6:
            mid = len(s) // 2
            return s[:mid] + "……" + s[mid:].rstrip("。！？") + "？"
        parts = []
        for i, c in enumerate(clauses):
            c = c.rstrip("，。！？")
            if i == 0 and len(clauses) > 1:
                parts.append(c + "……")
            elif i == len(clauses) - 1:
                parts.append(c + ("？" if key == "nervous" else "！"))
            else:
                parts.append(c + "，")
        return "".join(parts)

    if key == "comfort":
        parts = []
        for i, c in enumerate(clauses):
            c = c.rstrip("，。！？")
            if i < len(clauses) - 1:
                parts.append(c + "，")
            else:
                parts.append(c + "。")
        return "".join(parts)

    # calm / default
    parts = []
    for i, c in enumerate(clauses):
        c = c.rstrip("，。！？")
        if i < len(clauses) - 1:
            parts.append(c + "，")
        else:
            parts.append(c + "。")
    return "".join(parts)


def _subject_has_person_signal(subject: str) -> bool:
    t = (subject or "").strip()
    if not t:
        return False
    for token in (
        "博主",
        "手部模特",
        "模特",
        "主播",
        "出镜",
        "人物",
        "人脸",
    ):
        if token in t:
            return True
    return False


def build_delivery_prompt(
    *,
    environment: str,
    shot_intent: str,
    emotion: str,
    tone_label: str,
    performed: str,
    delivery: Dict[str, str],
    language: str = "zh",
    voiceover_mode: VoiceoverMode = VoiceoverMode.ON_SCREEN,
    requires_generic_person: bool = False,
    subject: str = "",
) -> str:
    """KOC / 画外音场景包裹模板。"""
    if voiceover_mode == VoiceoverMode.NONE or not (performed or "").strip():
        return ""

    effective_mode = voiceover_mode
    if requires_generic_person:
        effective_mode = VoiceoverMode.ON_SCREEN
    elif (
        not _subject_has_person_signal(subject)
        and voiceover_mode == VoiceoverMode.OFF_SCREEN
    ):
        effective_mode = VoiceoverMode.OFF_SCREEN

    lang = (language or "zh").strip().lower()
    preset_key = resolve_emotion_key(emotion)
    if is_non_chinese_voiceover(lang):
        env = (environment or "everyday indoor scene").strip()
        intent = (shot_intent or "sharing the product with viewers").strip()
        tone = (tone_label or "casual friend sharing").strip()
        preset = EMOTION_DELIVERY_PRESETS_EN.get(preset_key, EMOTION_DELIVERY_PRESETS_EN["calm"])
        vol = delivery.get("volume") or preset.get("volume", "")
        pace = delivery.get("pace") or preset.get("pace", "")
        pause = delivery.get("pause") or preset.get("pause", "")
        stress = delivery.get("stress") or preset.get("stress", "")
        tail = delivery.get("tail") or preset.get("tail", "")
        if effective_mode == VoiceoverMode.OFF_SCREEN:
            return (
                f"Voice-over narration only, no on-screen speaker, no lip-sync. "
                f"{vol}, {pace}, {pause}, {stress}, {tail}, "
                f"speaking in a {tone} tone: [{performed}]"
            )
        return (
            f"Creator in {env}, {intent}. "
            f"{vol}, {pace}, {pause}, {stress}, {tail}, "
            f"speaking in a {tone} tone: [{performed}]"
        )

    env = (environment or "日常室内场景").strip()
    intent = (shot_intent or "向观众分享产品").strip()
    tone = (tone_label or "朋友随口分享").strip()
    preset = EMOTION_DELIVERY_PRESETS.get(preset_key, EMOTION_DELIVERY_PRESETS["calm"])

    vol = delivery.get("volume") or preset.get("volume", "")
    pace = delivery.get("pace") or preset.get("pace", "")
    pause = delivery.get("pause") or preset.get("pause", "")
    stress = delivery.get("stress") or preset.get("stress", "")
    tail = delivery.get("tail") or preset.get("tail", "")

    if effective_mode == VoiceoverMode.OFF_SCREEN:
        return (
            f"画外音旁白，无人物出镜，无口型。"
            f"{vol}，{pace}，{pause}，{stress}，{tail}，"
            f"语气{tone}：【{performed}】"
        )

    return (
        f"博主在{env}，{intent}。"
        f"{vol}，{pace}，{pause}，{stress}，{tail}，"
        f"语气{tone}地说：【{performed}】"
    )
