"""按 DNA 节奏规划 Seedance 切段（每段 ≤ max_sec）。"""
from __future__ import annotations

from typing import List

from app.services.viral_studio.schemas import PlannedSegment, VideoDNA

MIN_SEGMENT_SEC = 2.0
DEFAULT_MAX_SEGMENT_SEC = 15.0


def _merge_close_points(points: List[float], min_gap: float = 2.0) -> List[float]:
    if not points:
        return []
    sorted_pts = sorted(set(float(p) for p in points if p is not None))
    out = [sorted_pts[0]]
    for p in sorted_pts[1:]:
        if p - out[-1] >= min_gap:
            out.append(p)
    return out


def _collect_cut_candidates(dna: VideoDNA) -> List[float]:
    candidates: List[float] = [0.0]
    for bp in dna.rhythm.beat_points_sec or []:
        candidates.append(float(bp))
    for tr in dna.transitions or []:
        candidates.append(float(tr.at_sec))
    for entry in dna.timeline or []:
        candidates.append(float(entry.end))
    duration = float(dna.meta.duration_sec or 0)
    if duration > 0:
        candidates.append(duration)
    return _merge_close_points(candidates, min_gap=1.0)


def plan_segments(
    dna: VideoDNA,
    *,
    max_segment_sec: float = DEFAULT_MAX_SEGMENT_SEC,
) -> List[PlannedSegment]:
    duration = float(dna.meta.duration_sec or 0)
    if duration <= 0 and dna.timeline:
        duration = max(float(e.end) for e in dna.timeline)
    if duration <= 0:
        duration = 15.0

    max_seg = min(float(max_segment_sec), DEFAULT_MAX_SEGMENT_SEC)
    if duration <= max_seg:
        return [
            PlannedSegment(
                index=0,
                start_sec=0.0,
                end_sec=round(duration, 2),
                duration=round(duration, 2),
            )
        ]

    candidates = _collect_cut_candidates(dna)
    if duration not in candidates:
        candidates.append(duration)
    candidates = sorted(set(candidates))
    candidates = [c for c in candidates if 0 <= c <= duration + 0.01]
    if not candidates or candidates[-1] < duration - 0.01:
        candidates.append(duration)

    segments: List[PlannedSegment] = []
    start = 0.0
    idx = 0

    while start < duration - 0.01:
        ideal_end = min(start + max_seg, duration)
        best_end = ideal_end
        # 在 (start+MIN, start+max_seg] 内找最接近 ideal 的候选切点
        window = [c for c in candidates if start + MIN_SEGMENT_SEC <= c <= start + max_seg + 0.01]
        if window:
            best_end = min(window, key=lambda c: abs(c - ideal_end))
        else:
            best_end = min(start + max_seg, duration)

        seg_dur = best_end - start
        remainder = duration - best_end

        if remainder > 0.01 and remainder < MIN_SEGMENT_SEC:
            # 避免产生过短尾段：若合并后不超过 max_seg，则一次切到 duration
            if (duration - start) <= max_seg + 0.01:
                best_end = duration
                seg_dur = best_end - start
            elif seg_dur + remainder <= max_seg + 0.01:
                best_end = duration
                seg_dur = best_end - start
            else:
                # 将尾段留给上一段末尾，提前切点
                best_end = max(start + MIN_SEGMENT_SEC, duration - MIN_SEGMENT_SEC)
                best_end = min(best_end, start + max_seg)
                seg_dur = best_end - start

        if seg_dur < MIN_SEGMENT_SEC and segments:
            # 合并到上一段（若可能）
            prev = segments[-1]
            merged_end = min(prev.end_sec + seg_dur, duration)
            if merged_end - prev.start_sec <= max_seg:
                prev.end_sec = round(merged_end, 2)
                prev.duration = round(merged_end - prev.start_sec, 2)
                start = merged_end
                continue

        if seg_dur < MIN_SEGMENT_SEC:
            best_end = min(start + MIN_SEGMENT_SEC, duration)

        segments.append(
            PlannedSegment(
                index=idx,
                start_sec=round(start, 2),
                end_sec=round(best_end, 2),
                duration=round(best_end - start, 2),
            )
        )
        idx += 1
        start = best_end

    for i, seg in enumerate(segments):
        seg.index = i
        if seg.duration > max_seg + 0.01:
            raise ValueError(f"段 {i} 时长 {seg.duration}s 超过上限 {max_seg}s")

    # 尾段过短则合并到上一段（若合并后仍 ≤ max_seg）
    if len(segments) >= 2 and segments[-1].duration < MIN_SEGMENT_SEC:
        tail = segments.pop()
        prev = segments[-1]
        merged_dur = tail.end_sec - prev.start_sec
        if merged_dur <= max_seg + 0.01:
            prev.end_sec = tail.end_sec
            prev.duration = round(merged_dur, 2)
        else:
            segments.append(tail)

    for i, seg in enumerate(segments):
        seg.index = i

    return segments
