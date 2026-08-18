"""Small statistical helpers."""

from __future__ import annotations

import statistics
from typing import Sequence


def _is_text_entity(entity: dict) -> bool:
    """文字判定与标注链路一致：优先 shape_type；无抽象类型时再认 DXF 文字类型。"""
    shape_type = str(entity.get("shape_type") or "")
    if shape_type:
        return shape_type == "text"
    return entity.get("entity_type") in {"TEXT", "MTEXT"}


def median_char_height(
    entities: Sequence[dict],
    fallback: float = 10.0,
) -> float:
    heights = [
        float(e["char_height"])
        for e in entities
        if _is_text_entity(e) and float(e.get("char_height") or 0) > 0
    ]
    if not heights:
        return float(fallback)
    return float(statistics.median(heights))


def percentile(values: Sequence[float], pct: float) -> float:
    """Inclusive percentile for a non-empty sequence (pct in 0..100)."""
    if not values:
        raise ValueError("percentile requires a non-empty sequence")
    xs = sorted(float(v) for v in values)
    if len(xs) == 1:
        return xs[0]
    p = max(0.0, min(100.0, float(pct)))
    rank = (len(xs) - 1) * p / 100.0
    lo = int(rank)
    hi = min(lo + 1, len(xs) - 1)
    w = rank - lo
    return xs[lo] * (1.0 - w) + xs[hi] * w
