"""Facility primitive helpers: stats and caption normalize (no DXF I/O)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.stats import median_char_height as _median_char_height
from utils.text_clean import clean_text

from config import Stage2Config


def median_char_height(primitives: list[dict], cfg: Stage2Config) -> float:
    return _median_char_height(primitives, fallback=float(cfg.fallback_char_height))


def median_facility_size(primitives: list[dict], facility_layer: str) -> float | None:
    sizes = [
        float(p["size"])
        for p in primitives
        if p.get("layer") == facility_layer
        and p.get("entity_type") in {"LINE", "LWPOLYLINE", "ARC", "CIRCLE", "INSERT"}
        and float(p.get("size") or 0) > 0
    ]
    if not sizes:
        return None
    sizes.sort()
    return float(sizes[len(sizes) // 2])


def normalize_caption(text: str) -> str:
    return clean_text(text).replace(" ", "")
