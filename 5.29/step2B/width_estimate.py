"""Corridor width estimation from straight-wall or endpoint segment geometry."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np

from stage2.graph_usage import info_list_from_endpoint_graph
from stage2.io import load_json
from step2B.paths import step2b_output_dir, straight_wall_geometry_json
from utils.scale import DEFAULT_MEDIAN_WIDTH, percentile
from utils.segment_geometry import acute_angle_deg, overlap_ratio, unit

WIDTH_MIN_SCALE = 0.5
WIDTH_MAX_SCALE = 1.6
DEFAULT_ANGLE_TH_DEG = 5.0
DEFAULT_MIN_OVERLAP_RATIO = 0.4
PROBE_MIN_WIDTH = 1.0
PROBE_MAX_WIDTH = 20.0


def _ensure_segment(row: dict[str, Any]) -> dict[str, Any]:
  seg = dict(row)
  start = np.asarray(seg["start"], dtype=float)[:2]
  end = np.asarray(seg["end"], dtype=float)[:2]
  seg["start"] = start
  seg["end"] = end
  vec = end - start
  length = float(seg.get("length") or np.linalg.norm(vec))
  if "direction" in seg and seg["direction"] is not None:
    direction = unit(np.asarray(seg["direction"], dtype=float)[:2])
  else:
    direction = unit(vec)
  seg["direction"] = direction
  seg["length"] = length
  if seg.get("mid") is not None:
    seg["mid"] = np.asarray(seg["mid"], dtype=float)[:2]
  else:
    seg["mid"] = (start + end) / 2.0
  seg["endpoints"] = (start, end)
  return seg


def segments_from_wall_doc(wall_doc: dict[str, Any]) -> list[dict[str, Any]]:
  out: list[dict[str, Any]] = []
  for row in wall_doc.get("walls") or []:
    attrs = row.get("attributes") or {}
    if attrs.get("start") is None or attrs.get("end") is None:
      continue
    out.append(_ensure_segment({
      "start": attrs["start"],
      "end": attrs["end"],
    }))
  return out


def segments_from_endpoint_info(info: list[dict[str, Any]]) -> list[dict[str, Any]]:
  return [_ensure_segment(row) for row in info]


def _signed_lateral(a: dict[str, Any], b: dict[str, Any]) -> float:
  normal = np.array([-a["direction"][1], a["direction"][0]])
  return float(np.dot(b["mid"] - a["mid"], normal))


def sample_nearest_opposite_widths(
  segments: list[dict[str, Any]],
  *,
  angle_th_deg: float = DEFAULT_ANGLE_TH_DEG,
  min_overlap_ratio: float = DEFAULT_MIN_OVERLAP_RATIO,
  probe_min: float = PROBE_MIN_WIDTH,
  probe_max: float = PROBE_MAX_WIDTH,
) -> dict[str, Any]:
  """
  法向最近邻对侧墙采样。

  对每段几何：先做夹角与投影重叠筛选，再在法向正、负两侧各保留
  横向距离最近的候选；同侧更远候选不进入宽度样本。
  """
  segs = [_ensure_segment(row) for row in segments]
  n = len(segs)
  samples: list[dict[str, Any]] = []

  for ia in range(n):
    a = segs[ia]
    best_pos: tuple[float, int] | None = None
    best_neg: tuple[float, int] | None = None

    for ib in range(n):
      if ia == ib:
        continue
      b = segs[ib]
      if acute_angle_deg(a["direction"], b["direction"]) >= angle_th_deg:
        continue
      if overlap_ratio(a, b) < min_overlap_ratio:
        continue
      signed = _signed_lateral(a, b)
      dist = abs(signed)
      if dist <= probe_min or dist >= probe_max:
        continue
      if signed > 0:
        if best_pos is None or dist < best_pos[0]:
          best_pos = (dist, ib)
      else:
        if best_neg is None or dist < best_neg[0]:
          best_neg = (dist, ib)

    for side_name, best in (("positive", best_pos), ("negative", best_neg)):
      if best is None:
        continue
      dist, ib = best
      samples.append({
        "segment_index": ia,
        "other_index": ib,
        "side": side_name,
        "width": round(dist, 6),
        "overlap_ratio": round(overlap_ratio(a, segs[ib]), 6),
      })

  widths = sorted(float(s["width"]) for s in samples)
  stats: dict[str, float | int | None] = {
    "sample_count": len(widths),
    "median": round(statistics.median(widths), 6) if widths else None,
    "p25": round(percentile(widths, 25), 6) if widths else None,
    "p75": round(percentile(widths, 75), 6) if widths else None,
    "p90": round(percentile(widths, 90), 6) if widths else None,
    "min": round(widths[0], 6) if widths else None,
    "max": round(widths[-1], 6) if widths else None,
  }
  return {
    "samples": samples,
    "widths": widths,
    "stats": stats,
  }


def estimate_corridor_width_median(
  segments: list[dict[str, Any]],
  *,
  angle_th_deg: float = DEFAULT_ANGLE_TH_DEG,
  min_overlap_ratio: float = DEFAULT_MIN_OVERLAP_RATIO,
) -> float:
  """Median of nearest-opposite width samples."""
  result = sample_nearest_opposite_widths(
    segments,
    angle_th_deg=angle_th_deg,
    min_overlap_ratio=min_overlap_ratio,
  )
  median = result["stats"].get("median")
  if median is None:
    return DEFAULT_MEDIAN_WIDTH
  return float(median)


def estimate_corridor_width_from_walls(wall_doc: dict[str, Any]) -> float:
  return estimate_corridor_width_median(segments_from_wall_doc(wall_doc))


def estimate_corridor_width_from_endpoint_graph(
  graph: nx.Graph,
  info: list[dict[str, Any]] | None = None,
) -> float:
  rows = info if info is not None else info_list_from_endpoint_graph(graph)
  return estimate_corridor_width_median(segments_from_endpoint_info(rows))


def load_corridor_width_median(
  stem: str,
  step2b_dir: Path | None = None,
) -> float:
  """Median nearest-opposite width from Step 2B straight wall geometry."""
  walls_path = straight_wall_geometry_json(stem, step2b_output_dir(step2b_dir))
  if not walls_path.is_file():
    return DEFAULT_MEDIAN_WIDTH
  wall_doc = load_json(walls_path)
  return estimate_corridor_width_from_walls(wall_doc)


def estimate_mean_corridor_width(
  graph: nx.Graph,
  info: list[dict[str, Any]],
  *,
  min_width: float = 3.0,
  max_width: float = 20.0,
  neighbor_gap: float | None = None,
) -> float:
  """Backward-compatible alias: nearest-opposite sampling on endpoint segments."""
  del min_width, max_width, neighbor_gap
  return estimate_corridor_width_from_endpoint_graph(graph, info)


def apply_width_band(
  cfg: object,
  median_width: float,
  *,
  min_scale: float = WIDTH_MIN_SCALE,
  max_scale: float = WIDTH_MAX_SCALE,
) -> float:
  """Set min_width / max_width on ParallelGraphConfig or CorridorDetectConfig."""
  setattr(cfg, "min_width", max(1.0, median_width * min_scale))
  setattr(cfg, "max_width", median_width * max_scale)
  return median_width
