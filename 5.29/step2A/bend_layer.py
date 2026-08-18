"""
Unified bend detection on the endpoint graph.

Topology layer (once): ``detect_bends`` → ``attach_bend_markers_to_graph``.
Inference layers (many):
  Step 2A — ``blocked_line_pairs_from_graph``
  Step 2B — ``residual_bend_doc_from_graph``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

import numpy as np

from utils.segment_geometry import acute_angle_deg as _angle_deg, unit as _unit
from stage2.geometry import (
  CorridorPipelineConfig,
  build_endpoint_graph,
  extract_primitive_info,
  filter_degenerate_segments,
)
from stage2.graph_usage import info_list_from_endpoint_graph


@dataclass
class BendLayerConfig:
  # 与 CorridorPipelineConfig.endpoint_link_gap 保持一致；勿在分步脚本另写默认值。
  endpoint_link_gap: float = 1.0
  angle_th_deg: float = 5.0
  colinear_angle_deg: float = 6.0
  min_bend_deg: float = 8.0
  max_bend_deg: float = 172.0
  # Square bend: endpoints must coincide within this (not full link gap).
  square_junction_tol: float = 1.0
  # Small arcs: treat as square-like corners (extend adjacent lines to meet).
  small_arc_radius_max: float = 5.0
  small_arc_chord_max: float = 10.0
  # Dimensionless multipliers; absolute values filled by apply_drawing_scale().
  local_band_scale: float = 0.5
  ix_sanity_chord_scale: float = 4.0
  ix_sanity_gap_scale: float = 2.0
  stub_chord_fraction: float = 0.45
  stub_p10_multiplier: float = 2.0
  endpoint_cluster_chord_scale: float = 0.15
  endpoint_cluster_radius_scale: float = 0.20
  endpoint_cluster_floor: float = 0.05
  clip_lateral_radius_scale: float = 0.35
  small_arc_chord_scale: float = 1.0
  small_arc_radius_scale: float = 1.0
  junction_radius_scale: float = 0.35
  # Resolved from drawing statistics (see drawing_scale.py).
  median_line_length: float = 0.0
  p10_line_length: float = 0.0
  p25_line_length: float = 0.0
  median_arc_chord: float = 0.0
  median_arc_radius: float = 0.0
  arc_chord_stub_max_len: float = 0.0
  arc_endpoint_cluster_tol: float = 0.0
  local_band_tol: float = 4.0
  ix_sanity_max_dist: float = 16.0
  clip_lateral_tol: float = 1.0
  min_line_extend_len: float = 16.0


def _seg_kind(seg: dict[str, Any]) -> str:
  return str(seg.get("type", "line")).lower()


def _is_colinear_continuation(angle_deg: float, tol_deg: float) -> bool:
  acute = min(angle_deg, 180.0 - angle_deg)
  return acute <= tol_deg


def _member_dict(handle: str, role: str) -> dict[str, str]:
  return {"handle": str(handle), "role": role}


def _member_handles(marker: dict[str, Any]) -> list[str]:
  members = marker.get("members", [])
  if not members:
    return []
  if isinstance(members[0], dict):
    return [str(m["handle"]) for m in members]
  return [str(h) for h in members]


def _line_handles_in_marker(marker: dict[str, Any]) -> list[str]:
  members = marker.get("members", [])
  if not members:
    return []
  if isinstance(members[0], dict):
    return [str(m["handle"]) for m in members if m.get("role") == "line"]
  return [str(h) for h in members]


def iter_bend_markers(graph: Any) -> Iterator[dict[str, Any]]:
  raw = graph.graph.get("bend_markers")
  if isinstance(raw, dict):
    yield from raw.values()
  elif isinstance(raw, list):
    yield from raw


def _handle_to_nid(graph: Any) -> dict[str, int]:
  return {str(data["handle"]): int(nid) for nid, data in graph.nodes(data=True)}


def _line_intersection_2d(
  p1: np.ndarray,
  d1: np.ndarray,
  p2: np.ndarray,
  d2: np.ndarray,
) -> np.ndarray | None:
  cross = float(d1[0] * d2[1] - d1[1] * d2[0])
  if abs(cross) < 1e-12:
    return None
  diff = p2 - p1
  t = float(diff[0] * d2[1] - diff[1] * d2[0]) / cross
  return p1 + t * d1


def _line_tangent_at_arc_endpoint(
  line_i: int,
  arc_ep: np.ndarray,
  info: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray]:
  """Point on line at arc junction and inward unit tangent."""
  eps = info[line_i]["endpoints"]
  arc_ep = np.asarray(arc_ep, dtype=float)
  d0 = float(np.linalg.norm(eps[0] - arc_ep))
  d1 = float(np.linalg.norm(eps[1] - arc_ep))
  if d0 <= d1:
    junc, other = eps[0], eps[1]
  else:
    junc, other = eps[1], eps[0]
  junc = np.asarray(junc, dtype=float)
  other = np.asarray(other, dtype=float)
  return junc, _unit(junc - other)


def _arc_chord_length(arc_i: int, info: list[dict[str, Any]]) -> float:
  ep0 = np.asarray(info[arc_i]["endpoints"][0], dtype=float)[:2]
  ep1 = np.asarray(info[arc_i]["endpoints"][1], dtype=float)[:2]
  return float(np.linalg.norm(ep1 - ep0))


def is_small_fillet_arc(
  arc_i: int,
  info: list[dict[str, Any]],
  cfg: BendLayerConfig | None = None,
) -> bool:
  """True when arc radius or chord is below small-arc thresholds."""
  cfg = cfg or BendLayerConfig()
  if _arc_chord_length(arc_i, info) <= cfg.small_arc_chord_max:
    return True
  radius = info[arc_i].get("radius")
  if radius is not None and float(radius) <= cfg.small_arc_radius_max:
    return True
  return False


def _fillet_tangent_intersection(
  la: int,
  lb: int,
  arc_i: int,
  info: list[dict[str, Any]],
  cfg: BendLayerConfig | None = None,
) -> np.ndarray | None:
  """
  Corner point for a fillet arc.

  Small arcs (short chord / small radius): extend adjacent line segments
  slightly until they meet (same as a square corner).
  Larger arcs: tangent-line intersection at the arc endpoints.
  """
  cfg = cfg or BendLayerConfig()
  ep0 = info[arc_i]["endpoints"][0]
  ep1 = info[arc_i]["endpoints"][1]
  p1, d1 = _line_tangent_at_arc_endpoint(la, ep0, info)
  p2, d2 = _line_tangent_at_arc_endpoint(lb, ep1, info)
  ix = _line_intersection_2d(p1, d1, p2, d2)
  if ix is not None:
    return ix
  if is_small_fillet_arc(arc_i, info, cfg):
    _, junction = _line_pair_junction(la, lb, info)
    return junction
  return None


def _line_pair_junction(
  la: int,
  lb: int,
  info: list[dict[str, Any]],
) -> tuple[float, np.ndarray]:
  """Minimum endpoint gap between two lines and the midpoint of the closest pair."""
  best = float("inf")
  junction = np.zeros(2, dtype=float)
  for p in info[la]["endpoints"]:
    p = np.asarray(p, dtype=float)[:2]
    for q in info[lb]["endpoints"]:
      q = np.asarray(q, dtype=float)[:2]
      d = float(np.linalg.norm(p - q))
      if d < best:
        best = d
        junction = (p + q) / 2.0
  return best, junction


def fillet_arc_plausible_at_corner(
  la: int,
  lb: int,
  arc_i: int,
  info: list[dict[str, Any]],
  *,
  junction_tol: float = 1.0,
  attach_ratio: float = 1.5,
) -> bool:
  """
  True when the arc chord sits at the line-pair corner, not merely within
  endpoint-link range of unrelated segments.
  """
  gap, junction = _line_pair_junction(la, lb, info)
  ep0 = np.asarray(info[arc_i]["endpoints"][0], dtype=float)[:2]
  ep1 = np.asarray(info[arc_i]["endpoints"][1], dtype=float)[:2]
  chord = float(np.linalg.norm(ep1 - ep0))
  mid = (ep0 + ep1) / 2.0
  attach_tol = max(chord * attach_ratio, junction_tol + 0.5)
  d_mid = float(np.linalg.norm(mid - junction))

  if gap <= junction_tol:
    d0 = float(np.linalg.norm(ep0 - junction))
    d1 = float(np.linalg.norm(ep1 - junction))
    return min(d0, d1, d_mid) <= attach_tol

  return d_mid <= attach_tol


def arc_endpoint_near_point(
  arc_i: int,
  info: list[dict[str, Any]],
  point: np.ndarray,
  *,
  tol: float,
) -> bool:
  """Whether either arc endpoint lies within ``tol`` of ``point``."""
  tol_sq = tol * tol
  point = np.asarray(point, dtype=float)[:2]
  for ep in info[arc_i]["endpoints"]:
    ep = np.asarray(ep, dtype=float)[:2]
    if float(np.dot(ep - point, ep - point)) <= tol_sq:
      return True
  return False


def should_block_merge(marker: dict[str, Any]) -> bool:
  """Whether this bend marker should block colinear wall merge (Step 2A)."""
  return marker.get("kind") in ("fillet", "square")


def _lines_at_endpoint(
  arc_i: int,
  ep_i: int,
  info: list[dict[str, Any]],
  endpoint_graph: Any,
  gap: float,
) -> list[int]:
  ep = info[arc_i]["endpoints"][ep_i]
  gap_sq = gap * gap
  found: list[int] = []
  for nb in endpoint_graph.neighbors(arc_i):
    if _seg_kind(info[nb]) != "line":
      continue
    for nb_ep in info[nb]["endpoints"]:
      if float(np.dot(ep - nb_ep, ep - nb_ep)) <= gap_sq:
        found.append(nb)
        break
  return found


def _drop_arc_chord_stubs(
  indices: list[int],
  dists: dict[int, float],
  info: list[dict[str, Any]],
  cfg: BendLayerConfig,
) -> list[int]:
  """
  Drop chord-length DXF stubs at an arc endpoint when a longer wall shares
  the same junction cluster (drawing-relative, not a fixed metre cutoff).
  """
  if len(indices) <= 1:
    return indices

  stub_max = cfg.arc_chord_stub_max_len
  cluster_tol = cfg.arc_endpoint_cluster_tol
  if stub_max <= 0.0 or cluster_tol <= 0.0:
    return indices

  best_d = min(dists[i] for i in indices)
  cluster = [i for i in indices if dists[i] <= best_d + cluster_tol]
  if len(cluster) <= 1:
    return indices

  long_in_cluster = [
    i for i in cluster
    if float(info[i].get("length", 0.0)) >= stub_max
  ]
  if not long_in_cluster:
    return indices

  drop = {
    i for i in cluster
    if float(info[i].get("length", 0.0)) < stub_max
  }
  if not drop:
    return indices
  return [i for i in indices if i not in drop]


def _line_endpoint_dist_to_point(
  line_i: int,
  point: np.ndarray,
  info: list[dict[str, Any]],
) -> float:
  """Minimum distance from a LINE endpoint to ``point``."""
  p0 = np.asarray(info[line_i]["endpoints"][0], dtype=float)[:2]
  p1 = np.asarray(info[line_i]["endpoints"][1], dtype=float)[:2]
  pt = np.asarray(point, dtype=float)[:2]
  return min(float(np.linalg.norm(pt - p0)), float(np.linalg.norm(pt - p1)))


def _local_line_candidates_at_arc_endpoint(
  arc_i: int,
  end_id: int,
  info: list[dict[str, Any]],
  endpoint_graph: Any,
  cfg: BendLayerConfig,
) -> list[int]:
  """
  Lines at one arc endpoint within a distance band.

  Step 1: keep candidates with d <= min(d) + local_band_tol.
  Step 2: drop chord stubs inside the same junction cluster.
  Step 3: length only breaks ties inside the band (sort key).
  """
  gap = cfg.endpoint_link_gap
  cand = _lines_at_endpoint(arc_i, end_id, info, endpoint_graph, gap)
  cand = [i for i in cand if _seg_kind(info[i]) == "line"]
  if not cand:
    return []

  ep = info[arc_i]["endpoints"][end_id]
  dists = {i: _line_endpoint_dist_to_point(i, ep, info) for i in cand}
  best_d = min(dists.values())
  band_tol = cfg.local_band_tol if cfg.local_band_tol > 0.0 else gap * cfg.local_band_scale
  near = [i for i in cand if dists[i] <= best_d + band_tol]
  near = _drop_arc_chord_stubs(near, dists, info, cfg)
  near.sort(key=lambda i: (dists[i], -float(info[i].get("length", 0.0))))
  return near


def _pair_ix_at_arc(
  la: int,
  lb: int,
  arc_i: int,
  info: list[dict[str, Any]],
  gap: float,
) -> np.ndarray | None:
  """Tangent-extension intersection for a (line@ep0, line@ep1) pair."""
  cfg = BendLayerConfig(endpoint_link_gap=gap)
  return _fillet_tangent_intersection(la, lb, arc_i, info, cfg)


def _best_line_pair_at_arc(
  arc_i: int,
  info: list[dict[str, Any]],
  endpoint_graph: Any,
  cfg: BendLayerConfig,
) -> tuple[int, int] | None:
  """
  Pick the LINE pair across an arc by joint geometry, not max acute angle.

  Enumerate local candidates per endpoint, then rank pairs by:
    1) both ends close to arc (d0 + d1)
    2) intersection near arc midpoint
    3) deflection near 90° (fillet-like)
  """
  gap = cfg.endpoint_link_gap
  sides = [
    _local_line_candidates_at_arc_endpoint(arc_i, 0, info, endpoint_graph, cfg),
    _local_line_candidates_at_arc_endpoint(arc_i, 1, info, endpoint_graph, cfg),
  ]
  if not sides[0] or not sides[1]:
    return None

  ep0 = np.asarray(info[arc_i]["endpoints"][0], dtype=float)[:2]
  ep1 = np.asarray(info[arc_i]["endpoints"][1], dtype=float)[:2]
  arc_mid = (ep0 + ep1) * 0.5
  ix_sanity = cfg.ix_sanity_max_dist if cfg.ix_sanity_max_dist > 0.0 else gap * cfg.ix_sanity_gap_scale

  best: tuple[int, int] | None = None
  best_key: tuple[float, float, float] | None = None

  for la in sides[0]:
    for lb in sides[1]:
      if la == lb:
        continue

      d0 = _line_endpoint_dist_to_point(la, ep0, info)
      d1 = _line_endpoint_dist_to_point(lb, ep1, info)
      if d0 >= gap or d1 >= gap:
        continue

      ix = _pair_ix_at_arc(la, lb, arc_i, info, gap)
      if ix is None:
        continue
      ix = np.asarray(ix, dtype=float)[:2]

      dist_ix = float(np.linalg.norm(ix - arc_mid))
      if dist_ix > ix_sanity:
        continue
      ang = _angle_deg(info[la]["direction"], info[lb]["direction"])
      acute = min(ang, 180.0 - ang)
      angle_penalty = abs(acute - 90.0)

      key = (-(d0 + d1), -dist_ix, -angle_penalty)
      if best_key is None or key > best_key:
        best_key = key
        best = (la, lb)

  return best


def _detect_fillet_markers(
  info: list[dict[str, Any]],
  endpoint_graph: Any,
  cfg: BendLayerConfig,
) -> list[dict[str, Any]]:
  markers: list[dict[str, Any]] = []
  seen_arcs: set[str] = set()
  seq = 0

  for arc_i, seg in enumerate(info):
    if _seg_kind(seg) != "arc":
      continue
    arc_handle = str(seg["handle"])
    if arc_handle in seen_arcs:
      continue

    pair = _best_line_pair_at_arc(arc_i, info, endpoint_graph, cfg)
    if pair is None:
      continue
    la, lb = pair
    ha, hb = str(info[la]["handle"]), str(info[lb]["handle"])

    deflection = _angle_deg(info[la]["direction"], info[lb]["direction"])
    acute = min(deflection, 180.0 - deflection)
    if acute < cfg.min_bend_deg:
      continue

    anchor_pt = _fillet_tangent_intersection(la, lb, arc_i, info, cfg)
    if anchor_pt is None:
      continue

    seq += 1
    seen_arcs.add(arc_handle)
    markers.append({
      "id": f"Y{seq:04d}",
      "kind": "fillet",
      "members": [
        _member_dict(ha, "line"),
        _member_dict(arc_handle, "arc"),
        _member_dict(hb, "line"),
      ],
      "anchor": [float(anchor_pt[0]), float(anchor_pt[1])],
      "anchor_kind": "tangent_intersection",
      "deflection": round(acute, 2),
    })

  return markers


def _detect_square_markers(
  info: list[dict[str, Any]],
  endpoint_graph: Any,
  fillet_line_pairs: set[frozenset[str]],
  cfg: BendLayerConfig,
) -> list[dict[str, Any]]:
  markers: list[dict[str, Any]] = []
  seen_pairs: set[frozenset[str]] = set()
  gap_sq = cfg.endpoint_link_gap * cfg.endpoint_link_gap
  arc_near_tol = min(cfg.endpoint_link_gap * 0.45, 4.0)
  arc_near_sq = arc_near_tol * arc_near_tol
  seq = 0

  for i, seg in enumerate(info):
    if _seg_kind(seg) != "line":
      continue
    hi = str(seg["handle"])
    for ep_i, ep in enumerate(seg["endpoints"]):
      line_nbs: list[tuple[int, int]] = []
      arc_at_ep = False
      for nb in endpoint_graph.neighbors(i):
        if _seg_kind(info[nb]) == "arc":
          for arc_ep in info[nb]["endpoints"]:
            if float(np.dot(ep - arc_ep, ep - arc_ep)) <= arc_near_sq:
              arc_at_ep = True
              break
        elif _seg_kind(info[nb]) == "line" and nb != i:
          for nb_ep_i, nb_ep in enumerate(info[nb]["endpoints"]):
            if float(np.dot(ep - nb_ep, ep - nb_ep)) <= gap_sq:
              line_nbs.append((nb, nb_ep_i))
      if arc_at_ep:
        continue

      for j, ej in line_nbs:
        hj = str(info[j]["handle"])
        pair_key = frozenset({hi, hj})
        if pair_key in seen_pairs or pair_key in fillet_line_pairs:
          continue

        di = -info[i]["direction"] if ep_i == 0 else info[i]["direction"]
        dj = -info[j]["direction"] if ej == 0 else info[j]["direction"]
        ang = _angle_deg(di, dj)
        if _is_colinear_continuation(ang, cfg.colinear_angle_deg):
          continue
        acute = min(ang, 180.0 - ang)
        if acute < cfg.min_bend_deg or acute > cfg.max_bend_deg:
          continue

        junction_gap, junction_pt = _line_pair_junction(i, j, info)
        if junction_gap > cfg.square_junction_tol:
          continue

        seq += 1
        seen_pairs.add(pair_key)
        markers.append({
          "id": f"F{seq:04d}",
          "kind": "square",
          "members": [
            _member_dict(hi, "line"),
            _member_dict(hj, "line"),
          ],
          "anchor": [float(junction_pt[0]), float(junction_pt[1])],
          "anchor_kind": "shared_endpoint",
          "deflection": round(acute, 2),
        })

  return markers


def detect_bends(
  endpoint_graph: Any,
  cfg: BendLayerConfig | None = None,
) -> list[dict[str, Any]]:
  """Detect fillet and square bends on an existing endpoint graph (topology layer)."""
  cfg = cfg or BendLayerConfig()
  info = info_list_from_endpoint_graph(endpoint_graph)
  if not info:
    return []

  fillets = _detect_fillet_markers(info, endpoint_graph, cfg)
  fillet_line_pairs: set[frozenset[str]] = set()
  for marker in fillets:
    lines = _line_handles_in_marker(marker)
    if len(lines) == 2:
      fillet_line_pairs.add(frozenset(lines))

  squares = _detect_square_markers(
    info, endpoint_graph, fillet_line_pairs, cfg,
  )
  return fillets + squares


def attach_bend_markers_to_graph(
  endpoint_graph: Any,
  markers: list[dict[str, Any]],
) -> None:
  """Write bend markers and node/edge back-references onto the graph."""
  endpoint_graph.graph["bend_markers"] = {
    marker["id"]: marker for marker in markers
  }
  handle_to_nid = _handle_to_nid(endpoint_graph)

  for nid, data in endpoint_graph.nodes(data=True):
    data.pop("bend_ids", None)

  for marker in markers:
    mid = marker["id"]
    for handle in _member_handles(marker):
      nid = handle_to_nid.get(handle)
      if nid is None:
        continue
      bend_ids = endpoint_graph.nodes[nid].setdefault("bend_ids", [])
      if mid not in bend_ids:
        bend_ids.append(mid)

    if marker.get("kind") == "square":
      line_handles = _line_handles_in_marker(marker)
      if len(line_handles) != 2:
        continue
      u = handle_to_nid.get(line_handles[0])
      v = handle_to_nid.get(line_handles[1])
      if u is None or v is None or not endpoint_graph.has_edge(u, v):
        continue
      endpoint_graph.edges[u, v]["is_bend"] = True
      endpoint_graph.edges[u, v]["bend_id"] = mid
      endpoint_graph.edges[u, v]["deflection_deg"] = marker.get("deflection")


def detect_and_attach_bends(
  endpoint_graph: Any,
  cfg: BendLayerConfig | None = None,
) -> list[dict[str, Any]]:
  """Detect bends once and attach them to the endpoint graph."""
  markers = detect_bends(endpoint_graph, cfg)
  attach_bend_markers_to_graph(endpoint_graph, markers)
  return markers


def blocked_line_pairs_from_markers(
  markers: list[dict[str, Any]],
  graph: Any | None = None,
) -> set[frozenset[str]]:
  """Line-handle pairs that must not merge across a bend (Step 2A inference)."""
  pairs: set[frozenset[str]] = set()
  for marker in markers:
    if not should_block_merge(marker):
      continue
    lines = _line_handles_in_marker(marker)
    for i in range(len(lines)):
      for j in range(i + 1, len(lines)):
        pairs.add(frozenset({lines[i], lines[j]}))
  return pairs


def blocked_line_pairs_from_graph(endpoint_graph: Any) -> set[frozenset[str]]:
  """Step 2A: derive merge blockers from graph-attached bend markers."""
  return blocked_line_pairs_from_markers(list(iter_bend_markers(endpoint_graph)))
