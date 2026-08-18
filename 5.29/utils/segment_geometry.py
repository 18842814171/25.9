"""2D segment / centerline geometry shared across pipeline steps."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def unit(v: np.ndarray) -> np.ndarray:
  n = float(np.linalg.norm(v))
  if n < 1e-12:
    return np.array([1.0, 0.0])
  return v / n


def acute_angle_deg(d1: np.ndarray, d2: np.ndarray) -> float:
  dot = float(np.clip(abs(float(np.dot(unit(d1), unit(d2)))), -1.0, 1.0))
  return float(math.degrees(math.acos(dot)))


def cross2(a: np.ndarray, b: np.ndarray) -> float:
  return float(a[0] * b[1] - a[1] * b[0])


def projection_interval(
  start: np.ndarray,
  end: np.ndarray,
  origin: np.ndarray,
  axis: np.ndarray,
) -> tuple[float, float]:
  axis = unit(axis)
  ts = [float(np.dot(ep - origin, axis)) for ep in (start, end)]
  return min(ts), max(ts)


def projection_interval_on_segment(
  seg: dict[str, Any],
  origin: np.ndarray,
  axis: np.ndarray,
) -> tuple[float, float]:
  axis = unit(axis)
  ts = [float(np.dot(ep - origin, axis)) for ep in seg["endpoints"]]
  return min(ts), max(ts)


def clamp_point_to_segment(
  point: np.ndarray,
  start: np.ndarray,
  end: np.ndarray,
) -> np.ndarray:
  seg = end - start
  seg_len = float(np.linalg.norm(seg))
  if seg_len < 1e-12:
    return start.copy()
  u = seg / seg_len
  t = float(np.dot(point - start, u))
  t = max(0.0, min(seg_len, t))
  return start + u * t


def point_segment_distance(
  point: np.ndarray,
  start: np.ndarray,
  end: np.ndarray,
) -> float:
  point = np.asarray(point, dtype=float)[:2]
  start = np.asarray(start, dtype=float)[:2]
  end = np.asarray(end, dtype=float)[:2]
  seg = end - start
  seg_len = float(np.linalg.norm(seg))
  if seg_len < 1e-12:
    return float(np.linalg.norm(point - start))
  u = seg / seg_len
  t = float(np.dot(point - start, u))
  t = max(0.0, min(seg_len, t))
  proj = start + u * t
  return float(np.linalg.norm(point - proj))


def point_line_offset(
  point: np.ndarray,
  origin: np.ndarray,
  direction: np.ndarray,
) -> float:
  direction = unit(direction)
  diff = np.asarray(point, dtype=float)[:2] - np.asarray(origin, dtype=float)[:2]
  return abs(float(diff[0] * direction[1] - diff[1] * direction[0]))


def endpoint_gap(seg_a: dict[str, Any], seg_b: dict[str, Any]) -> float:
  best = float("inf")
  for pa in seg_a["endpoints"]:
    for pb in seg_b["endpoints"]:
      d = float(np.linalg.norm(np.asarray(pa) - np.asarray(pb)))
      if d < best:
        best = d
  return best


def overlap_ratio(seg_a: dict[str, Any], seg_b: dict[str, Any]) -> float:
  ref = seg_a if float(seg_a["length"]) >= float(seg_b["length"]) else seg_b
  other = seg_b if ref is seg_a else seg_a
  origin = np.asarray(ref["start"], dtype=float)[:2]
  axis = np.asarray(ref["direction"], dtype=float)[:2]
  a0, a1 = projection_interval_on_segment(ref, origin, axis)
  b0, b1 = projection_interval_on_segment(other, origin, axis)
  overlap = max(0.0, min(a1, b1) - max(a0, b0))
  shorter = min(float(a1 - a0), float(b1 - b0))
  if shorter < 1e-9:
    return 0.0
  return overlap / shorter


def parallel_pair_ok(
  seg_a: dict[str, Any],
  seg_b: dict[str, Any],
  *,
  angle_th_deg: float,
  min_width: float,
  max_width: float,
  min_overlap_ratio: float,
) -> tuple[bool, float, float]:
  if acute_angle_deg(seg_a["direction"], seg_b["direction"]) >= angle_th_deg:
    return False, 0.0, 0.0
  width = point_line_offset(seg_b["mid"], seg_a["start"], seg_a["direction"])
  if width < min_width or width > max_width:
    return False, width, 0.0
  overlap = overlap_ratio(seg_a, seg_b)
  if overlap < min_overlap_ratio:
    return False, width, overlap
  return True, width, overlap


def overlap_centerline(
  seg_a: dict[str, Any],
  seg_b: dict[str, Any],
) -> dict[str, Any] | None:
  ref, other = (seg_a, seg_b) if seg_a["length"] >= seg_b["length"] else (seg_b, seg_a)
  origin = np.asarray(ref["start"], dtype=float)[:2]
  axis = unit(np.asarray(ref["direction"], dtype=float)[:2])

  a0, a1 = projection_interval(ref["start"], ref["end"], origin, axis)
  b0, b1 = projection_interval(other["start"], other["end"], origin, axis)
  t0 = max(a0, b0)
  t1 = min(a1, b1)
  if t1 - t0 < 1e-6:
    return None

  def midpoint_at(t: float) -> np.ndarray:
    p_axis = origin + axis * t
    pa = clamp_point_to_segment(p_axis, seg_a["start"], seg_a["end"])
    pb = clamp_point_to_segment(p_axis, seg_b["start"], seg_b["end"])
    return (pa + pb) / 2.0

  start = midpoint_at(t0)
  end = midpoint_at(t1)
  vec = end - start
  length = float(np.linalg.norm(vec))
  if length < 1e-6:
    return None
  direction = vec / length
  return {
    "start": [round(float(start[0]), 4), round(float(start[1]), 4)],
    "end": [round(float(end[0]), 4), round(float(end[1]), 4)],
    "direction": [round(float(direction[0]), 6), round(float(direction[1]), 6)],
    "length": round(length, 4),
  }


def assign_left_right(
  wall_a: str,
  wall_b: str,
  seg_a: dict[str, Any],
  seg_b: dict[str, Any],
  centerline: dict[str, Any],
) -> tuple[str, str]:
  direction = np.asarray(centerline["direction"], dtype=float)[:2]
  vec = np.asarray(seg_b["mid"], dtype=float)[:2] - np.asarray(seg_a["mid"], dtype=float)[:2]
  if cross2(direction, vec) > 0.0:
    return wall_b, wall_a
  return wall_a, wall_b
