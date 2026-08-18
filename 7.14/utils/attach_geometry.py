"""Point-to-centerline geometry helpers."""

from __future__ import annotations

from typing import Any

import numpy as np


def point_to_segment(
    px: float,
    py: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> tuple[float, float, float, float]:
    """Return (distance, foot_x, foot_y, t) for point P to segment AB.

    Parameter t is clamped to [0, 1].
    """
    a = np.asarray([ax, ay], dtype=float)
    b = np.asarray([bx, by], dtype=float)
    p = np.asarray([px, py], dtype=float)
    ab = b - a
    length_sq = float(np.dot(ab, ab))
    if length_sq <= 1e-18:
        foot = a
        t = 0.0
    else:
        t = float(np.dot(p - a, ab) / length_sq)
        t = max(0.0, min(1.0, t))
        foot = a + t * ab
    dist = float(np.linalg.norm(p - foot))
    return dist, float(foot[0]), float(foot[1]), t


def nearest_centerline(
    px: float,
    py: float,
    centerlines: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Pick the nearest centerline record; each item needs id/start/end."""
    best: dict[str, Any] | None = None
    best_dist = float("inf")
    for item in centerlines:
        start = item["start"]
        end = item["end"]
        dist, fx, fy, t = point_to_segment(
            px, py, float(start[0]), float(start[1]), float(end[0]), float(end[1])
        )
        if dist < best_dist:
            best_dist = dist
            best = {
                "centerline_id": str(item["id"]),
                "distance": dist,
                "foot_x": fx,
                "foot_y": fy,
                "t": t,
                "role": item.get("role"),
                "width": item.get("width"),
            }
    return best
