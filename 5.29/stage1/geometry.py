"""Segment extraction and geometry statistics (JSON or in-memory primitives)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

MIN_SEG_LEN = 1e-4
CORRIDOR_WIDTH_MIN = 2.0
CORRIDOR_WIDTH_MAX = 10.0
PARALLEL_COS = 0.95
DIRECTION_BINS = 8


@dataclass
class Segment:
    start: np.ndarray
    end: np.ndarray
    mid: np.ndarray
    length: float
    direction: np.ndarray | None
    geo_type: str


@dataclass
class LayerGeomAccumulator:
  n_segments: int = 0
  total_length: float = 0.0
  lengths: list = field(default_factory=list)
  mids: list = field(default_factory=list)
  directions: list = field(default_factory=list)
  # DXF entity-type → summed path length (LINE / LWPOLYLINE / POLYLINE / ARC)
  length_by_type: dict = field(default_factory=dict)

  def add(self, seg: Segment, entity_type: str | None = None) -> None:
    if seg.length < MIN_SEG_LEN:
      return
    self.n_segments += 1
    self.total_length += seg.length
    self.lengths.append(seg.length)
    self.mids.append(seg.mid)
    if seg.direction is not None:
      self.directions.append(seg.direction)
    if entity_type:
      self.length_by_type[entity_type] = self.length_by_type.get(entity_type, 0.0) + seg.length


def _unit(v: np.ndarray) -> np.ndarray | None:
  n = float(np.linalg.norm(v))
  if n < 1e-8:
    return None
  return v / n


def segments_from_primitive(prim: dict[str, Any], approximate_arc: bool = True) -> list[Segment]:
  """Match logic in 0-巷道几何信息图谱.py extract_primitive_info."""
  typ = prim.get("type", "")
  attrs = prim.get("attributes") or {}
  handle = prim.get("handle", "unknown")
  out: list[Segment] = []

  def add_seg(s, e, geo_type: str, suffix: str = ""):
    s = np.asarray(s[:2], dtype=float)
    e = np.asarray(e[:2], dtype=float)
    length = float(np.linalg.norm(e - s))
    direction = _unit(e - s)
    out.append(
      Segment(
        start=s,
        end=e,
        mid=(s + e) / 2,
        length=length,
        direction=direction,
        geo_type=geo_type,
      )
    )

  if typ == "LINE":
    if "start" in attrs and "end" in attrs:
      add_seg(attrs["start"], attrs["end"], "line")
  elif typ == "ARC":
    if "start" in attrs and "end" in attrs:
      add_seg(attrs["start"], attrs["end"], "arc")
    elif approximate_arc and "center" in attrs and "radius" in attrs:
      c = np.array(attrs["center"][:2], dtype=float)
      r = float(attrs["radius"])
      sa = math.radians(attrs.get("start_angle", 0))
      ea = math.radians(attrs.get("end_angle", 360))
      add_seg(
        c + r * np.array([math.cos(sa), math.sin(sa)]),
        c + r * np.array([math.cos(ea), math.sin(ea)]),
        "arc",
      )
  elif typ == "LWPOLYLINE" and "points" in attrs:
    pts = [np.array(p[:2], dtype=float) for p in attrs["points"]]
    for k in range(len(pts) - 1):
      add_seg(pts[k], pts[k + 1], "line")
  elif typ == "POLYLINE" and "vertices" in attrs:
    verts = [np.array(v[:2], dtype=float) for v in attrs["vertices"]]
    for k in range(len(verts) - 1):
      add_seg(verts[k], verts[k + 1], "line")

  return out


def direction_histogram(directions: list[np.ndarray], n_bins: int = DIRECTION_BINS) -> list[float]:
  if not directions:
    return [0.0] * n_bins
  bins = [0] * n_bins
  for d in directions:
    ang = math.atan2(d[1], d[0]) % math.pi
    idx = min(int(ang / math.pi * n_bins), n_bins - 1)
    bins[idx] += 1
  total = sum(bins) or 1
  return [b / total for b in bins]


def parallel_pair_ratio(
  mids: list[np.ndarray],
  directions: list[np.ndarray],
  max_samples: int = 400,
) -> float:
  n = len(mids)
  if n < 2 or len(directions) < 2:
    return 0.0

  idx = list(range(min(n, len(directions))))
  if len(idx) > max_samples:
    rng = np.random.default_rng(0)
    idx = rng.choice(idx, size=max_samples, replace=False).tolist()

  pairs = 0
  parallel = 0
  for i in range(len(idx)):
    for j in range(i + 1, len(idx)):
      a, b = idx[i], idx[j]
      d1, d2 = directions[a], directions[b]
      if d1 is None or d2 is None:
        continue
      pairs += 1
      if abs(float(np.dot(d1, d2))) >= PARALLEL_COS:
        m1, m2 = mids[a], mids[b]
        normal = np.array([-d1[1], d1[0]])
        spacing = abs(float(np.dot(m2 - m1, normal)))
        if CORRIDOR_WIDTH_MIN <= spacing <= CORRIDOR_WIDTH_MAX:
          parallel += 1

  return parallel / pairs if pairs else 0.0


def summarize_geometry(acc: LayerGeomAccumulator) -> dict[str, Any]:
  lengths = acc.lengths
  length_by_type = {k: round(v, 3) for k, v in acc.length_by_type.items()}
  if not lengths:
    return {
      "n_segments": 0,
      "total_length": 0.0,
      "mean_length": 0.0,
      "std_length": 0.0,
      "max_length": 0.0,
      "direction_hist": [0.0] * DIRECTION_BINS,
      "parallel_pair_ratio": 0.0,
      "long_segment_ratio": 0.0,
      "length_by_type": length_by_type,
    }

  arr = np.array(lengths, dtype=float)
  long_thresh = float(np.percentile(arr, 75)) if len(arr) > 4 else float(arr.mean())
  long_ratio = float(np.mean(arr >= max(long_thresh, 3.0)))

  return {
    "n_segments": acc.n_segments,
    "total_length": round(acc.total_length, 3),
    "mean_length": round(float(arr.mean()), 3),
    "std_length": round(float(arr.std()), 3) if len(arr) > 1 else 0.0,
    "max_length": round(float(arr.max()), 3),
    "direction_hist": [round(x, 4) for x in direction_histogram(acc.directions)],
    "parallel_pair_ratio": round(parallel_pair_ratio(acc.mids, acc.directions), 4),
    "long_segment_ratio": round(long_ratio, 4),
    "length_by_type": length_by_type,
  }
