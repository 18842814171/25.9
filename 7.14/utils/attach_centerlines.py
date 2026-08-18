"""Centerline catalog and attach-distance threshold inference."""

from __future__ import annotations

from typing import Any, Iterable

import networkx as nx
import numpy as np

from utils.attach_geometry import nearest_centerline


def centerline_catalog(
    structure: nx.Graph,
    roles: tuple[str, ...] | list[str],
) -> list[dict[str, Any]]:
    role_set = set(roles)
    out: list[dict[str, Any]] = []
    for nid, data in structure.nodes(data=True):
        if data.get("node_type") != "centerline":
            continue
        role = str(data.get("role") or "")
        if role_set and role not in role_set:
            continue
        start = data.get("start")
        end = data.get("end")
        if start is None or end is None:
            continue
        out.append(
            {
                "id": str(nid),
                "start": start,
                "end": end,
                "role": role,
                "width": data.get("width"),
            }
        )
    return out


def infer_attach_threshold(
    structure: nx.Graph,
    anchor_points: Iterable[tuple[float, float]],
    centerlines: list[dict[str, Any]],
    *,
    outlier_cap_width_factor: float,
    attach_distance_percentile: float,
    attach_distance_width_factor: float,
    attach_distance_fallback: float,
) -> float:
    """Infer max attach distance from inlier nearest-centerline distances."""
    median_w = structure.graph.get("median_corridor_width")
    fallback = float(attach_distance_fallback)
    if median_w is not None:
        fallback = max(
            fallback,
            float(median_w) * float(attach_distance_width_factor),
        )
    if not centerlines:
        return fallback

    cap = fallback
    if median_w is not None:
        cap = float(median_w) * float(outlier_cap_width_factor)

    distances: list[float] = []
    for px, py in anchor_points:
        hit = nearest_centerline(float(px), float(py), centerlines)
        if hit is None:
            continue
        dist = float(hit["distance"])
        if dist <= cap:
            distances.append(dist)
    if len(distances) < 3:
        return fallback
    return float(np.percentile(distances, float(attach_distance_percentile)))
