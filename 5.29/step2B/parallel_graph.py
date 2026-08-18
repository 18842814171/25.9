"""Logical connection graph over straight walls and residual stubs."""

from __future__ import annotations

import math
import statistics
from typing import Any, Iterable

import networkx as nx
import numpy as np

from stage2.geometry import _iter_endpoint_adjacent_pairs
from step2B.config import ParallelGraphConfig
from step2B.width_estimate import WIDTH_MAX_SCALE, WIDTH_MIN_SCALE, apply_width_band
from utils.segment_geometry import (
  acute_angle_deg,
  endpoint_gap,
  parallel_pair_ok,
  point_line_offset,
  unit,
)


def _line_row_to_seg(
  row: dict[str, Any],
  *,
  node_id: str,
  node_type: str,
) -> dict[str, Any]:
  attrs = row.get("attributes") or {}
  start = np.asarray(attrs["start"], dtype=float)[:2]
  end = np.asarray(attrs["end"], dtype=float)[:2]
  vec = end - start
  length = float(np.linalg.norm(vec))
  direction = unit(vec) if length >= 1e-12 else np.array([1.0, 0.0])
  return {
    "node_id": node_id,
    "node_type": node_type,
    "start": start,
    "end": end,
    "mid": (start + end) / 2.0,
    "length": length,
    "direction": direction,
    "endpoints": [start, end],
    "members": list(row.get("members") or []),
    "handle": str(row.get("handle") or ""),
  }


def _collect_segments(
  wall_doc: dict[str, Any],
  residual_doc: dict[str, Any],
) -> list[dict[str, Any]]:
  segments: list[dict[str, Any]] = []
  for row in wall_doc.get("walls") or []:
    ws_id = str(row.get("wall_segment_id", ""))
    if not ws_id:
      continue
    segments.append(_line_row_to_seg(row, node_id=ws_id, node_type="wall"))
  for row in residual_doc.get("elements") or []:
    handle = str(row.get("handle", ""))
    if not handle:
      continue
    segments.append(_line_row_to_seg(row, node_id=handle, node_type="stub"))
  return segments


def _parallel_pair_ok(
  seg_a: dict[str, Any],
  seg_b: dict[str, Any],
  *,
  angle_th_deg: float,
  min_width: float,
  max_width: float,
  min_overlap_ratio: float,
) -> tuple[bool, float, float]:
  return parallel_pair_ok(
    seg_a,
    seg_b,
    angle_th_deg=angle_th_deg,
    min_width=min_width,
    max_width=max_width,
    min_overlap_ratio=min_overlap_ratio,
  )


def _iter_bbox_near_pairs(
  segments: list[dict[str, Any]],
  indices: Iterable[int],
  *,
  pad: float,
) -> list[tuple[int, int]]:
  """
  Segment index pairs whose AABBs come within ``pad`` (spatial hash).

  Prefer :func:`_iter_parallel_candidate_pairs` for long segments; AABB fill
  can explode when many long polylines share dense cells.
  """
  idx_list = list(indices)
  if len(idx_list) < 2 or pad < 0:
    return []

  cell = max(pad, 1e-6)
  inv = 1.0 / cell
  buckets: dict[tuple[int, int], list[int]] = {}

  for i in idx_list:
    seg = segments[i]
    xs = [float(seg["start"][0]), float(seg["end"][0])]
    ys = [float(seg["start"][1]), float(seg["end"][1])]
    x0 = min(xs) - pad
    x1 = max(xs) + pad
    y0 = min(ys) - pad
    y1 = max(ys) + pad
    cx0, cx1 = int(np.floor(x0 * inv)), int(np.floor(x1 * inv))
    cy0, cy1 = int(np.floor(y0 * inv)), int(np.floor(y1 * inv))
    for cx in range(cx0, cx1 + 1):
      for cy in range(cy0, cy1 + 1):
        buckets.setdefault((cx, cy), []).append(i)

  pairs: set[tuple[int, int]] = set()
  for members in buckets.values():
    uniq = sorted(set(members))
    for ai, a in enumerate(uniq):
      for b in uniq[ai + 1:]:
        pairs.add((a, b) if a < b else (b, a))
  return sorted(pairs)


def _iter_parallel_candidate_pairs(
  segments: list[dict[str, Any]],
  indices: Iterable[int] | None = None,
  *,
  min_width: float,
  max_width: float,
  angle_th_deg: float,
) -> list[tuple[int, int]]:
  """
  Candidate parallel pairs via direction bins + lateral/axial sweep.

  Keeps pairs whose midpoints lie in the width band and whose axial
  projection intervals overlap (overlap ratio checked later).
  """
  idx_list = list(indices) if indices is not None else list(range(len(segments)))
  if len(idx_list) < 2 or max_width < min_width:
    return []

  bin_deg = max(float(angle_th_deg), 1.0)
  n_bins = max(int(math.ceil(180.0 / bin_deg)), 1)
  bins: dict[int, list[int]] = {}
  for i in idx_list:
    d = np.asarray(segments[i]["direction"], dtype=float)[:2]
    ang = math.degrees(math.atan2(float(d[1]), float(d[0]))) % 180.0
    bins.setdefault(int(ang // bin_deg) % n_bins, []).append(i)

  pairs: set[tuple[int, int]] = set()

  def sweep(group: list[int], ref_dir: np.ndarray) -> None:
    if len(group) < 2:
      return
    axis = unit(np.asarray(ref_dir, dtype=float)[:2])
    normal = np.array([-float(axis[1]), float(axis[0])])
    items: list[tuple[float, float, float, int]] = []
    for i in group:
      mid = np.asarray(segments[i]["mid"], dtype=float)[:2]
      lat = float(np.dot(mid, normal))
      ts = [
        float(np.dot(np.asarray(ep, dtype=float)[:2] - mid, axis))
        for ep in segments[i]["endpoints"]
      ]
      # Store absolute axial coords so interval tests are consistent.
      t_mid = float(np.dot(mid, axis))
      t0, t1 = t_mid + min(ts), t_mid + max(ts)
      items.append((lat, t0, t1, i))
    items.sort()
    right = 0
    m = len(items)
    for left in range(m):
      lat_i, a0, a1, i = items[left]
      if right <= left:
        right = left + 1
      while right < m and items[right][0] - lat_i <= max_width:
        right += 1
      for k in range(left + 1, right):
        lat_j, b0, b1, j = items[k]
        if lat_j - lat_i < min_width:
          continue
        if min(a1, b1) - max(a0, b0) <= 0.0:
          continue
        pairs.add((i, j) if i < j else (j, i))

  for b in range(n_bins):
    here = bins.get(b, [])
    if len(here) >= 2:
      sweep(here, np.asarray(segments[here[0]]["direction"], dtype=float)[:2])
    nxt = bins.get((b + 1) % n_bins, [])
    if here and nxt:
      sweep(
        here + nxt,
        np.asarray(segments[here[0]]["direction"], dtype=float)[:2],
      )

  return sorted(pairs)


def _iter_endpoint_structure_pairs(
  segments: list[dict[str, Any]],
  endpoint_link_gap: float,
  *,
  angle_th_deg: float,
  colinear_lateral_tol: float,
) -> list[tuple[int, int, float, float]]:
  """
  Endpoint-adjacent pairs that are near-parallel or near-orthogonal only.

  Near-parallel pairs must also be nearly colinear (lateral offset below
  ``colinear_lateral_tol``); side-by-side corridor neighbors are excluded
  here and handled by parallel edges instead.
  """
  if not segments or endpoint_link_gap <= 0:
    return []

  bin_deg = max(float(angle_th_deg), 1.0)
  n_bins = max(int(math.ceil(180.0 / bin_deg)), 1)
  ortho_shift = max(int(round(90.0 / bin_deg)), 1) % n_bins

  bins: dict[int, list[int]] = {}
  for i, seg in enumerate(segments):
    d = np.asarray(seg["direction"], dtype=float)[:2]
    ang = math.degrees(math.atan2(float(d[1]), float(d[0]))) % 180.0
    bins.setdefault(int(ang // bin_deg) % n_bins, []).append(i)

  cell = max(endpoint_link_gap, 1e-6)
  inv = 1.0 / cell
  gap_sq = endpoint_link_gap * endpoint_link_gap
  out: dict[tuple[int, int], tuple[float, float]] = {}

  def match_groups(group_a: list[int], group_b: list[int], *, allow_same: bool) -> None:
    if not group_a or not group_b:
      return
    refs_b: list[tuple[int, np.ndarray]] = []
    buckets: dict[tuple[int, int], list[int]] = {}
    for seg_j in group_b:
      for ep in segments[seg_j]["endpoints"]:
        ref_idx = len(refs_b)
        pt = np.asarray(ep, dtype=float)[:2]
        refs_b.append((seg_j, pt))
        key = (int(np.floor(float(pt[0]) * inv)), int(np.floor(float(pt[1]) * inv)))
        buckets.setdefault(key, []).append(ref_idx)

    for seg_i in group_a:
      for ep in segments[seg_i]["endpoints"]:
        ep_a = np.asarray(ep, dtype=float)[:2]
        cx = int(np.floor(float(ep_a[0]) * inv))
        cy = int(np.floor(float(ep_a[1]) * inv))
        for dx in (-1, 0, 1):
          for dy in (-1, 0, 1):
            for ref_idx in buckets.get((cx + dx, cy + dy), ()):
              seg_j, ep_b = refs_b[ref_idx]
              if seg_i == seg_j:
                continue
              if allow_same and seg_i >= seg_j:
                continue
              if not allow_same and seg_i > seg_j:
                continue
              diff = ep_a - ep_b
              dist_sq = float(np.dot(diff, diff))
              if dist_sq > gap_sq:
                continue
              angle = acute_angle_deg(
                segments[seg_i]["direction"], segments[seg_j]["direction"],
              )
              is_para = angle < angle_th_deg
              is_ortho = abs(angle - 90.0) < angle_th_deg
              if not (is_para or is_ortho):
                continue
              if is_para:
                axis = unit(np.asarray(segments[seg_i]["direction"], dtype=float)[:2])
                mid_i = np.asarray(segments[seg_i]["mid"], dtype=float)[:2]
                mid_j = np.asarray(segments[seg_j]["mid"], dtype=float)[:2]
                ts_i = sorted(
                  float(np.dot(np.asarray(ep, dtype=float)[:2] - mid_i, axis))
                  for ep in segments[seg_i]["endpoints"]
                )
                ts_j = sorted(
                  float(np.dot(np.asarray(ep, dtype=float)[:2] - mid_j, axis))
                  for ep in segments[seg_j]["endpoints"]
                )
                ai0 = float(np.dot(mid_i, axis)) + ts_i[0]
                ai1 = float(np.dot(mid_i, axis)) + ts_i[-1]
                aj0 = float(np.dot(mid_j, axis)) + ts_j[0]
                aj1 = float(np.dot(mid_j, axis)) + ts_j[-1]
                # Overlapping axial spans are side-by-side neighbors, not continuation.
                if min(ai1, aj1) - max(ai0, aj0) > 1.0:
                  continue
                lat = point_line_offset(
                  mid_j,
                  segments[seg_i]["start"],
                  segments[seg_i]["direction"],
                )
                if lat > colinear_lateral_tol:
                  continue
              key = (seg_i, seg_j) if seg_i < seg_j else (seg_j, seg_i)
              gap = math.sqrt(dist_sq)
              prev = out.get(key)
              if prev is None or gap < prev[0]:
                out[key] = (gap, angle)

  for b in range(n_bins):
    here = bins.get(b, [])
    if len(here) >= 2:
      match_groups(here, here, allow_same=True)
    nxt = bins.get((b + 1) % n_bins, [])
    if here and nxt:
      match_groups(here, nxt, allow_same=False)
    ortho = bins.get((b + ortho_shift) % n_bins, [])
    if here and ortho:
      match_groups(here, ortho, allow_same=False)

  return [(i, j, gap, ang) for (i, j), (gap, ang) in out.items()]


def _add_or_upgrade_parallel_edge(
  graph: nx.Graph,
  seg_a: dict[str, Any],
  seg_b: dict[str, Any],
  width: float,
  overlap: float,
) -> None:
  u, v = seg_a["node_id"], seg_b["node_id"]
  if graph.has_edge(u, v):
    graph[u][v]["edge_kind"] = "endpoint_parallel"
    graph[u][v]["is_parallel"] = True
    graph[u][v]["width"] = round(width, 4)
    graph[u][v]["overlap_ratio"] = round(overlap, 4)
  else:
    graph.add_edge(
      u,
      v,
      edge_kind="is_parallel",
      width=round(width, 4),
      overlap_ratio=round(overlap, 4),
      is_parallel=True,
    )


def _parallel_edge_widths(graph: nx.Graph) -> list[float]:
  widths: list[float] = []
  for _u, _v, data in graph.edges(data=True):
    if not data.get("is_parallel"):
      continue
    if data.get("width") is None:
      continue
    widths.append(float(data["width"]))
  return widths


def prune_parallel_edges_by_width(
  graph: nx.Graph,
  *,
  min_width: float,
  max_width: float,
) -> int:
  """Drop or downgrade is_parallel edges whose width falls outside the band."""
  removed = 0
  for u, v, data in list(graph.edges(data=True)):
    if not data.get("is_parallel"):
      continue
    if data.get("width") is None:
      continue
    width = float(data["width"])
    if min_width <= width <= max_width:
      continue
    if data.get("edge_kind") == "endpoint_parallel" or "endpoint_gap" in data:
      data["edge_kind"] = "endpoint"
      data["is_parallel"] = False
      data.pop("width", None)
      data.pop("overlap_ratio", None)
    else:
      graph.remove_edge(u, v)
    removed += 1
  return removed


def refine_parallel_edges_by_width_percentile(
  graph: nx.Graph,
  cfg: ParallelGraphConfig,
  *,
  min_scale: float = WIDTH_MIN_SCALE,
  max_scale: float = WIDTH_MAX_SCALE,
) -> float | None:
  """
  From proposed parallel-edge widths, take the median as corridor scale,
  set cfg min/max band, and delete edges that are too far / too near.
  """
  widths = _parallel_edge_widths(graph)
  if not widths:
    return None
  median = float(statistics.median(widths))
  apply_width_band(cfg, median, min_scale=min_scale, max_scale=max_scale)
  prune_parallel_edges_by_width(
    graph,
    min_width=float(cfg.min_width),
    max_width=float(cfg.max_width),
  )
  graph.graph["estimated_corridor_width"] = round(median, 4)
  graph.graph["width_band"] = {
    "min_width": float(cfg.min_width),
    "max_width": float(cfg.max_width),
  }
  return median


def build_parallel_graph(
  wall_doc: dict[str, Any],
  residual_doc: dict[str, Any],
  cfg: ParallelGraphConfig | None = None,
  *,
  search_min_width: float | None = None,
  search_max_width: float | None = None,
) -> nx.Graph:
  """Build logical graph: nodes wall/stub; edges endpoint and is_parallel.

  Endpoint edges: local endpoint neighborhood (``endpoint_link_gap``).

  Parallel edges (first pass): wall–wall pairs that are near-parallel with
  projection overlap, inside a loose lateral search radius
  (``probe_*`` / ``search_*``). Callers may then refine by width percentile.
  """
  cfg = cfg or ParallelGraphConfig()
  min_w = float(cfg.probe_min_width if search_min_width is None else search_min_width)
  max_w = float(cfg.probe_max_width if search_max_width is None else search_max_width)
  segments = _collect_segments(wall_doc, residual_doc)
  graph = nx.Graph()
  graph.graph["kind"] = "parallel_graph"
  graph.graph["parallel_search"] = {
    "min_width": min_w,
    "max_width": max_w,
  }

  for seg in segments:
    graph.add_node(
      seg["node_id"],
      node_type=seg["node_type"],
      start=[float(seg["start"][0]), float(seg["start"][1])],
      end=[float(seg["end"][0]), float(seg["end"][1])],
      length=float(seg["length"]),
      direction=[float(seg["direction"][0]), float(seg["direction"][1])],
      members=seg["members"],
      handle=seg["handle"],
    )

  for i, j in _iter_endpoint_adjacent_pairs(segments, cfg.endpoint_link_gap):
    seg_a, seg_b = segments[i], segments[j]
    gap = endpoint_gap(seg_a, seg_b)
    if gap > cfg.endpoint_link_gap:
      continue
    angle = acute_angle_deg(seg_a["direction"], seg_b["direction"])
    graph.add_edge(
      seg_a["node_id"],
      seg_b["node_id"],
      edge_kind="endpoint",
      endpoint_gap=round(gap, 4),
      angle_deg=round(angle, 4),
      is_parallel=angle < cfg.angle_th_deg,
      is_ortho=abs(angle - 90.0) < cfg.angle_th_deg,
    )

  wall_indices = [
    i for i, seg in enumerate(segments) if seg["node_type"] == "wall"
  ]
  for i, j in _iter_parallel_candidate_pairs(
    segments,
    wall_indices,
    min_width=min_w,
    max_width=max_w,
    angle_th_deg=float(cfg.angle_th_deg),
  ):
    seg_a, seg_b = segments[i], segments[j]
    ok, width, overlap = _parallel_pair_ok(
      seg_a,
      seg_b,
      angle_th_deg=float(cfg.angle_th_deg),
      min_width=min_w,
      max_width=max_w,
      min_overlap_ratio=float(cfg.min_overlap_ratio),
    )
    if not ok:
      continue
    _add_or_upgrade_parallel_edge(graph, seg_a, seg_b, width, overlap)

  return graph


def parallel_wall_groups(graph: nx.Graph) -> list[list[str]]:
  """Connected components among wall nodes linked by is_parallel."""
  para = nx.Graph()
  for node, data in graph.nodes(data=True):
    if data.get("node_type") == "wall":
      para.add_node(node)
  for u, v, data in graph.edges(data=True):
    if not data.get("is_parallel"):
      continue
    if para.has_node(u) and para.has_node(v):
      para.add_edge(u, v)
  return [sorted(comp) for comp in nx.connected_components(para)]


def parallel_graph_summary(
  graph: nx.Graph,
  *,
  source_stem: str,
  cfg: ParallelGraphConfig,
  estimated_corridor_width: float | None = None,
) -> dict[str, Any]:
  groups = parallel_wall_groups(graph)
  doc: dict[str, Any] = {
    "kind": "parallel_graph_summary",
    "schema_version": 1,
    "source_stem": source_stem,
    "config": cfg.to_json(),
    "node_count": graph.number_of_nodes(),
    "edge_count": graph.number_of_edges(),
    "wall_count": sum(
      1 for _, d in graph.nodes(data=True) if d.get("node_type") == "wall"
    ),
    "stub_count": sum(
      1 for _, d in graph.nodes(data=True) if d.get("node_type") == "stub"
    ),
    "parallel_group_count": len(groups),
    "parallel_groups": [
      {"group_id": f"PG{idx:03d}", "wall_segment_ids": group}
      for idx, group in enumerate(groups, start=1)
    ],
  }
  if estimated_corridor_width is not None:
    doc["estimated_corridor_width"] = round(estimated_corridor_width, 4)
  return doc
