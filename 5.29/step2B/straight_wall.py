"""Straight wall segment detection on normalized_graph (angle_deg on edges)."""

from __future__ import annotations

import math

from typing import Any, Iterator

import networkx as nx
import numpy as np

from stage2.graph_usage import info_list_from_endpoint_graph
from step2B.config import StraightWallConfig
from utils.segment_geometry import point_line_offset, unit as _unit


def _lateral_offset_between_segments(
  seg_a: dict[str, Any],
  seg_b: dict[str, Any],
) -> float:
  """Max perpendicular distance of either segment mid to the other's wall line."""
  start_a = np.asarray(seg_a["start"], dtype=float)[:2]
  dir_a = np.asarray(seg_a["direction"], dtype=float)[:2]
  start_b = np.asarray(seg_b["start"], dtype=float)[:2]
  dir_b = np.asarray(seg_b["direction"], dtype=float)[:2]
  mid_a = np.asarray(seg_a["mid"], dtype=float)[:2]
  mid_b = np.asarray(seg_b["mid"], dtype=float)[:2]
  off_a = point_line_offset(mid_a, start_b, dir_b)
  off_b = point_line_offset(mid_b, start_a, dir_a)
  return max(off_a, off_b)


def _iter_local_endpoint_neighbors(
  graph: nx.Graph,
  node: int,
) -> Iterator[tuple[int, dict[str, Any]]]:
  """Yield undirected endpoint-neighbors already present on the endpoint graph."""
  if not graph.has_node(node):
    alt = str(node)
    if not graph.has_node(alt):
      return
    node_key: int | str = alt
  else:
    node_key = node
  for nb in graph.neighbors(node_key):
    vi = int(nb)
    if vi <= int(node):
      continue
    data = graph[node_key][nb]
    if data.get("edge_kind") != "endpoint":
      continue
    yield vi, data


def _edge_mergeable(
  edge_data: dict[str, Any],
  seg_a: dict[str, Any],
  seg_b: dict[str, Any],
  cfg: StraightWallConfig,
) -> bool:
  """True when two endpoint-adjacent segments may join one straight wall."""
  angle = float(edge_data.get("angle_deg", 90.0))
  if angle >= cfg.continuity_angle_deg:
    return False

  lateral = _lateral_offset_between_segments(seg_a, seg_b)
  if lateral > cfg.continuity_lateral_tol:
    return False

  return True


def _chain_colinear(members: list[dict[str, Any]], cfg: StraightWallConfig) -> bool:
  """All segments in chain point along the same wall line."""
  if len(members) <= 1:
    return True
  ref = _unit(np.asarray(members[0]["direction"], dtype=float)[:2])
  for seg in members[1:]:
    d = _unit(np.asarray(seg["direction"], dtype=float)[:2])
    dot = abs(float(np.dot(ref, d)))
    acute = math.degrees(math.acos(min(dot, 1.0)))
    if min(acute, 180.0 - acute) >= cfg.continuity_angle_deg:
      return False
  return True


def _members_form_straight_wall(
  members: list[dict[str, Any]],
  cfg: StraightWallConfig,
) -> bool:
  """True when members may occupy one exclusive straight-wall group."""
  if len(members) <= 1:
    return True
  if not _chain_colinear(members, cfg):
    return False
  longest = max(members, key=lambda m: float(m.get("length", 0.0)))
  origin = np.asarray(longest["start"], dtype=float)[:2]
  direction = _unit(np.asarray(longest["direction"], dtype=float)[:2])
  for seg in members:
    mid = np.asarray(seg["mid"], dtype=float)[:2]
    if point_line_offset(mid, origin, direction) > cfg.continuity_lateral_tol:
      return False
  return True


def _colinear_chains(
  graph: nx.Graph,
  info: list[dict[str, Any]],
  cfg: StraightWallConfig,
) -> list[list[int]]:
  """
  Exclusive straight-wall groups via claim-and-merge.

  Each LINE index belongs to at most one group. Mergeable endpoint edges are
  considered in priority order; two groups unite only when the combined
  members stay colinear within angle/lateral tolerances. Rejected edges leave
  both sides unchanged, so a junction segment is never shared across groups.
  """
  n = len(info)
  if n == 0:
    return []

  parent = list(range(n))
  members: list[list[int]] = [[i] for i in range(n)]

  def find(x: int) -> int:
    while parent[x] != x:
      parent[x] = parent[parent[x]]
      x = parent[x]
    return x

  merge_edges: list[tuple[float, float, int, int]] = []
  for ui in range(n):
    for vi, data in _iter_local_endpoint_neighbors(graph, ui):
      if not _edge_mergeable(data, info[ui], info[vi], cfg):
        continue
      angle = float(data.get("angle_deg", 90.0))
      min_len = min(float(info[ui]["length"]), float(info[vi]["length"]))
      # Stronger (smaller angle) and longer overlaps first.
      merge_edges.append((angle, -min_len, ui, vi))
  merge_edges.sort()

  for _angle, _neg_len, ui, vi in merge_edges:
    ru, rv = find(ui), find(vi)
    if ru == rv:
      continue
    combined = members[ru] + members[rv]
    if not _members_form_straight_wall([info[i] for i in combined], cfg):
      continue
    # Claim: attach rv under ru; members of rv are no longer independent.
    parent[rv] = ru
    members[ru] = combined
    members[rv] = []

  chains = [m for root, m in enumerate(members) if parent[root] == root and m]
  return chains


def _envelope_endpoints(
  members: list[dict[str, Any]],
) -> tuple[list[float], list[float]]:
  """Colinear envelope start/end from member segment endpoints."""
  longest = max(members, key=lambda m: float(m.get("length", 0.0)))
  direction = _unit(np.asarray(longest["direction"], dtype=float)[:2])
  origin = np.asarray(longest["start"], dtype=float)[:2]

  projections: list[tuple[float, np.ndarray]] = []
  for seg in members:
    for ep in seg["endpoints"]:
      p = np.asarray(ep, dtype=float)[:2]
      t = float(np.dot(p - origin, direction))
      projections.append((t, p))

  projections.sort(key=lambda x: x[0])
  start = projections[0][1]
  end = projections[-1][1]
  return [float(start[0]), float(start[1])], [float(end[0]), float(end[1])]


def detect_wall_segments(
  graph: nx.Graph,
  cfg: StraightWallConfig | None = None,
) -> list[dict[str, Any]]:
  """
  Find straight-wall groups on normalized_graph.

  Each LINE belongs to at most one group. Groups grow by claim-and-merge along
  endpoint-adjacent colinear edges (angle + lateral); junctions do not share
  a segment across multiple walls.
  """
  cfg = cfg or StraightWallConfig()
  info = info_list_from_endpoint_graph(graph)
  if not info:
    return []

  chain_ids = _colinear_chains(graph, info, cfg)

  segments: list[dict[str, Any]] = []
  for member_ids in chain_ids:
    members = [info[i] for i in member_ids]
    handles = sorted(str(m["handle"]) for m in members)
    start, end = _envelope_endpoints(members)
    segments.append({
      "members": handles,
      "start": start,
      "end": end,
    })

  segments.sort(key=lambda s: s["members"][0])
  for idx, seg in enumerate(segments, start=1):
    seg["wall_segment_id"] = f"WS{idx:03d}"

  return segments


def _primitive_to_segment_info(prim: dict[str, Any]) -> dict[str, Any]:
  attrs = prim.get("attributes") or {}
  start = np.asarray(attrs["start"], dtype=float)[:2]
  end = np.asarray(attrs["end"], dtype=float)[:2]
  length = float(np.linalg.norm(end - start))
  if length < 1e-12:
    direction = np.array([1.0, 0.0])
  else:
    direction = (end - start) / length
  return {
    "handle": str(prim.get("handle", "")),
    "start": start,
    "end": end,
    "mid": (start + end) / 2.0,
    "length": length,
    "direction": direction,
    "endpoints": [start, end],
  }


def merge_primitives_to_endpoints(
  primitives: list[dict[str, Any]],
) -> tuple[list[float], list[float]]:
  """Merge LINE primitives along colinear envelope (farthest endpoints)."""
  if not primitives:
    raise ValueError("merge_primitives_to_endpoints requires at least one LINE")
  if len(primitives) == 1:
    attrs = primitives[0].get("attributes") or {}
    s = attrs["start"]
    e = attrs["end"]
    return [float(s[0]), float(s[1])], [float(e[0]), float(e[1])]
  members = [_primitive_to_segment_info(p) for p in primitives]
  return _envelope_endpoints(members)


def _primitive_length(prim: dict[str, Any]) -> float:
  attrs = prim.get("attributes") or {}
  start = np.asarray(attrs.get("start", [0, 0]), dtype=float)[:2]
  end = np.asarray(attrs.get("end", [0, 0]), dtype=float)[:2]
  return float(np.linalg.norm(end - start))


def _segment_max_member_length(
  seg: dict[str, Any],
  prim_by_handle: dict[str, dict[str, Any]],
) -> float:
  lengths = [
    _primitive_length(prim_by_handle[h])
    for h in (seg.get("members") or [])
    if str(h) in prim_by_handle
  ]
  return max(lengths) if lengths else 0.0


def is_straight_wall_segment(
  seg: dict[str, Any],
  prim_by_handle: dict[str, dict[str, Any]],
  *,
  short_length_thresh: float,
) -> bool:
  """
  True when a detected group belongs in straight_wall_geometry (not residual).

  Multi-member merges always qualify; single-member groups need length above
  the short threshold (``TH_TIMES × median corridor width``, default 5×).
  """
  members = list(seg.get("members") or [])
  if len(members) > 1:
    return True
  return _segment_max_member_length(seg, prim_by_handle) > short_length_thresh


def merge_wall_segments_to_geometry(
  segments: list[dict[str, Any]],
  prim_by_handle: dict[str, dict[str, Any]],
  *,
  short_length_thresh: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
  """
  Build merged straight-wall LINE records and residual primitives.

  Straight walls go to ``walls``; short single-member groups go to ``residual``.
  """
  walls: list[dict[str, Any]] = []
  residual: list[dict[str, Any]] = []

  for seg in segments:
    handles = [str(h) for h in seg.get("members") or []]
    prims = [prim_by_handle[h] for h in handles if h in prim_by_handle]
    if not prims:
      continue
    if not is_straight_wall_segment(
      seg, prim_by_handle, short_length_thresh=short_length_thresh,
    ):
      residual.extend(prims)
      continue
    start, end = merge_primitives_to_endpoints(prims)
    row: dict[str, Any] = {
      "wall_segment_id": str(seg["wall_segment_id"]),
      "members": handles,
      "type": "LINE",
      "attributes": {
        "start": [start[0], start[1], 0.0],
        "end": [end[0], end[1], 0.0],
      },
    }
    layer = prims[0].get("layer")
    if layer is not None:
      row["layer"] = layer
    walls.append(row)

  residual.sort(key=lambda p: str(p.get("handle", "")))
  return walls, residual


def straight_wall_geometry_to_json(
  walls: list[dict[str, Any]],
  *,
  source_stem: str,
) -> dict[str, Any]:
  return {
    "kind": "straight_wall_geometry",
    "schema_version": 1,
    "source_stem": source_stem,
    "walls": walls,
  }


def residual_geometry_to_json(
  elements: list[dict[str, Any]],
  *,
  source_stem: str,
) -> dict[str, Any]:
  return {
    "kind": "residual_geometry",
    "schema_version": 1,
    "source_stem": source_stem,
    "elements": elements,
  }


def wall_segments_to_json(
  segments: list[dict[str, Any]],
  *,
  source_stem: str,
  cfg: StraightWallConfig,
) -> dict[str, Any]:
  return {
    "kind": "wall_segment",
    "schema_version": 1,
    "source_stem": source_stem,
    "config": cfg.to_json(),
    "segments": segments,
  }
