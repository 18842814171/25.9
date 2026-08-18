"""Geometry fingerprints and scale-normalized distances."""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.stats import median_char_height


def dist(a: dict, b: dict) -> float:
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["y"]) - float(b["y"]))


def norm_radius(radius: float, char_height: float) -> float:
    h = max(float(char_height), 1e-6)
    return float(radius) / h


def circle_matches(
    candidate_radius: float,
    template_r_norms: list[float],
    char_height: float,
    rel_tol: float = 0.55,
) -> bool:
    if not template_r_norms:
        return False
    rn = norm_radius(candidate_radius, char_height)
    for tr in template_r_norms:
        if tr <= 0:
            continue
        if abs(rn - tr) / tr <= rel_tol:
            return True
    return False


def block_matches(block_name: str | None, template_blocks: list[str]) -> bool:
    if not block_name:
        return False
    return block_name in set(template_blocks)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] * (c - k) + xs[c] * (k - f)


def merge_unique(seq: list[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[str] = set()
    for item in seq:
        key = repr(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
