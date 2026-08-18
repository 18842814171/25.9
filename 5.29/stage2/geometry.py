"""Shared geometry primitives: primitive extraction and endpoint graph."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np


def _unit(v: np.ndarray | None) -> np.ndarray | None:
  if v is None:
    return None
  n = float(np.linalg.norm(v))
  return v / n if n > 1e-8 else None


@dataclass
class CorridorPipelineConfig:
  min_length_filter: float = 1e-4
  dist_th: float = 20.0
  angle_th_deg: float = 5.0
  endpoint_tol: float = 1e-3
  # Pass 1 geometry graph: connect broken same-wall segments at endpoints.
  # 顶层唯一默认值；分步脚本不得另设 3.0 / 8.0 等硬编码。
  endpoint_link_gap: float = 1.0
  continuity_angle_deg: float = 5.0
  # Max lateral offset when chaining colinear segments (avoids merging opposite walls).
  continuity_lateral_tol: float = 1.0
  min_width: float = 1.0
  max_width: float = 3.0
  min_overlap_ratio: float = 0.4
  min_corridor_length: float = 2.0
  logical_hops: int = 3
  # Do not colinear-merge across endpoint clusters with this many segments.
  junction_block_degree: int = 3
  # 剔除相对主体图幅飞出的异常图元（错误坐标 / 超长串线）。
  spatial_outlier_filter: bool = True
  spatial_outlier_percentile_low: float = 5.0
  spatial_outlier_percentile_high: float = 95.0
  spatial_outlier_pad_ratio: float = 1.0


def _percentile_sorted(values: list[float], pct: float) -> float:
  if not values:
    return 0.0
  ordered = sorted(values)
  if len(ordered) == 1:
    return float(ordered[0])
  rank = (len(ordered) - 1) * (pct / 100.0)
  lo = int(rank)
  hi = min(lo + 1, len(ordered) - 1)
  frac = rank - lo
  return float(ordered[lo] * (1.0 - frac) + ordered[hi] * frac)


def _primitive_xy_points(prim: dict) -> list[np.ndarray]:
  attrs = prim.get("attributes") or {}
  pts: list[np.ndarray] = []
  for key in ("start", "end", "center"):
    if key in attrs and attrs[key] is not None:
      pts.append(np.asarray(attrs[key][:2], dtype=float))
  for pt in attrs.get("points") or []:
    pts.append(np.asarray(pt[:2], dtype=float))
  return pts


def filter_spatial_outliers(
  primitives: list[dict],
  *,
  percentile_low: float = 5.0,
  percentile_high: float = 95.0,
  pad_ratio: float = 1.0,
) -> tuple[list[dict], list[dict]]:
  """Drop primitives whose centroid lies far outside the core drawing bbox.

  Core box = [p_low, p_high] of all sampled coordinates, expanded by
  ``pad_ratio * span``. Returns ``(kept, dropped)``.
  """
  sample_x: list[float] = []
  sample_y: list[float] = []
  centers: list[np.ndarray | None] = []
  for prim in primitives:
    pts = _primitive_xy_points(prim)
    if not pts:
      centers.append(None)
      continue
    for p in pts:
      sample_x.append(float(p[0]))
      sample_y.append(float(p[1]))
    centers.append(np.mean(np.stack(pts, axis=0), axis=0))

  if len(sample_x) < 8:
    return list(primitives), []

  x0 = _percentile_sorted(sample_x, percentile_low)
  x1 = _percentile_sorted(sample_x, percentile_high)
  y0 = _percentile_sorted(sample_y, percentile_low)
  y1 = _percentile_sorted(sample_y, percentile_high)
  pad_x = max((x1 - x0) * pad_ratio, 1.0)
  pad_y = max((y1 - y0) * pad_ratio, 1.0)
  x0 -= pad_x
  x1 += pad_x
  y0 -= pad_y
  y1 += pad_y

  kept: list[dict] = []
  dropped: list[dict] = []
  for prim, center in zip(primitives, centers):
    if center is None:
      kept.append(prim)
      continue
    cx, cy = float(center[0]), float(center[1])
    if x0 <= cx <= x1 and y0 <= cy <= y1:
      kept.append(prim)
    else:
      dropped.append(prim)
  return kept, dropped


def filter_degenerate_segments(primitives: list[dict], min_length: float = 1e-4) -> list[dict]:
  valid: list[dict] = []
  for p in primitives:
    if p["type"] not in ("LINE", "ARC", "LINE_FROM_ARC"):
      valid.append(p)
      continue
    attrs = p.get("attributes", {})
    if "start" not in attrs or "end" not in attrs:
      valid.append(p)
      continue
    s = np.array(attrs["start"][:2])
    e = np.array(attrs["end"][:2])
    if np.linalg.norm(e - s) >= min_length:
      valid.append(p)
  return valid


def _append_layer(row: dict[str, Any], prim: dict[str, Any]) -> None:
  layer = prim.get("layer")
  if layer is not None:
    row["layer"] = layer


def extract_primitive_info(primitives: list[dict], approximate_arc: bool = True) -> list[dict]:
  segments: list[dict] = []
  for prim in primitives:
    typ = prim["type"]
    attrs = prim.get("attributes", {})
    handle = prim.get("handle", "unknown")

    start = None
    end = None

    if typ in ("LINE", "LINE_FROM_ARC"):
      start = np.array(attrs["start"][:2])
      end = np.array(attrs["end"][:2])
    elif typ == "ARC":
      if "start" in attrs and "end" in attrs:
        start = np.array(attrs["start"][:2])
        end = np.array(attrs["end"][:2])
      elif approximate_arc:
        center = np.array(attrs["center"][:2])
        radius = attrs["radius"]
        sa = math.radians(attrs.get("start_angle", 0))
        ea = math.radians(attrs.get("end_angle", 360))
        start = center + radius * np.array([math.cos(sa), math.sin(sa)])
        end = center + radius * np.array([math.cos(ea), math.sin(ea)])
      else:
        continue
    elif typ == "CIRCLE":
      center = np.array(attrs["center"][:2])
      radius = attrs["radius"]
      start = center + np.array([-radius, 0])
      end = center + np.array([radius, 0])
    elif typ == "LWPOLYLINE" and "points" in attrs:
      pts = [np.array(p[:2]) for p in attrs["points"]]
      for k in range(len(pts) - 1):
        s, e = pts[k], pts[k + 1]
        length = float(np.linalg.norm(e - s))
        if length < 1e-8:
          continue
        direction = (e - s) / length
        segments.append({
          "handle": f"{handle}_seg{k}",
          "type": "line",
          "start": s,
          "end": e,
          "mid": (s + e) / 2,
          "length": length,
          "direction": direction,
          "endpoints": [s, e],
        })
        _append_layer(segments[-1], prim)
      continue
    else:
      continue

    if start is None or end is None:
      continue

    length = float(np.linalg.norm(end - start))
    if length < 1e-8:
      continue
    direction = (end - start) / length
    seg_type = "line" if typ == "LINE_FROM_ARC" else typ
    row: dict[str, Any] = {
      "handle": handle,
      "type": seg_type,
      "start": start,
      "end": end,
      "mid": (start + end) / 2,
      "length": length,
      "direction": direction,
      "endpoints": [start, end],
    }
    if typ == "LINE_FROM_ARC" and attrs.get("source_arc"):
      row["source_arc"] = str(attrs["source_arc"])
    segments.append(row)
    _append_layer(segments[-1], prim)
  return segments


def _spatial_grid_buckets(
  info: list[dict],
  cell_size: float,
  *,
  position_key: str = "mid",
) -> dict[tuple[int, int], list[int]]:
  """Bucket segment indices by midpoint (default) or other ndarray field."""
  buckets: dict[tuple[int, int], list[int]] = {}
  inv = 1.0 / max(cell_size, 1e-6)
  for i, d in enumerate(info):
    pos = d[position_key]
    key = (int(np.floor(pos[0] * inv)), int(np.floor(pos[1] * inv)))
    buckets.setdefault(key, []).append(i)
  return buckets


def _endpoint_gap_nodes(nu: dict, nv: dict) -> float:
  pts1 = [nu["start"], nu["end"]]
  pts2 = [nv["start"], nv["end"]]
  return min(float(np.linalg.norm(p1 - p2)) for p1 in pts1 for p2 in pts2)


def _directions_close(d1: np.ndarray, d2: np.ndarray, angle_tol_rad: float) -> bool:
  return abs(float(np.dot(_unit(d1), _unit(d2)))) > float(np.cos(angle_tol_rad))


def _edge_angle_flags(
  ni: dict,
  nj: dict,
  *,
  angle_th_deg: float,
  endpoint_tol: float,
) -> dict[str, Any] | None:
  """Shared acute-angle / endpoint-gap flags for segment-pair edges."""
  d1, d2 = ni.get("direction"), nj.get("direction")
  if d1 is None or d2 is None:
    return None

  endpoint_gap = _endpoint_gap_nodes(ni, nj)
  is_shared = endpoint_gap < endpoint_tol

  dot = float(np.clip(np.dot(d1, d2), -1.0, 1.0))
  angle_deg = float(np.degrees(np.arccos(dot)))
  min_angle_deg = min(angle_deg, 180.0 - angle_deg)
  is_para = min_angle_deg < angle_th_deg
  is_ortho = abs(min_angle_deg - 90.0) < angle_th_deg

  return {
    "endpoint_gap": round(endpoint_gap, 4),
    "angle_deg": round(min_angle_deg, 4),
    "is_shared": bool(is_shared),
    "is_para": bool(is_para),
    "is_ortho": bool(is_ortho),
  }


def _endpoint_edge_relations(
  ni: dict,
  nj: dict,
  *,
  angle_th_deg: float,
  endpoint_tol: float,
) -> dict[str, Any] | None:
  """Canonical endpoint-graph edge attrs (no midpoint-derived fields)."""
  return _edge_angle_flags(
    ni,
    nj,
    angle_th_deg=angle_th_deg,
    endpoint_tol=endpoint_tol,
  )


def _geometry_edge_relations(
  ni: dict,
  nj: dict,
  *,
  angle_th_deg: float,
  endpoint_tol: float,
) -> dict[str, Any] | None:
  """
  Parallel-graph edge relation data aligned with ``old/0-巷道几何信息图谱.py``.

  Includes midpoint delta / length ratio for corridor pairing heuristics only.
  """
  base = _edge_angle_flags(
    ni,
    nj,
    angle_th_deg=angle_th_deg,
    endpoint_tol=endpoint_tol,
  )
  if base is None:
    return None

  delta = nj["mid"] - ni["mid"]
  mid_dist = float(np.linalg.norm(delta))

  len_i = float(ni.get("length", 0.0))
  len_j = float(nj.get("length", 0.0))
  denom = len_i + len_j
  r_ij = len_i / denom if denom > 0 else 0.5
  features = np.array([
    float(delta[0]),
    float(delta[1]),
    base["angle_deg"] * math.pi / 180.0,
    r_ij,
    float(base["is_para"]),
    float(base["is_ortho"]),
    float(base["is_shared"]),
  ])

  return {
    **base,
    "delta": delta.tolist(),
    "mid_dist": round(mid_dist, 4),
    "r_ij": round(r_ij, 4),
    "features": features,
  }


def _add_geometry_edge(
  graph: nx.Graph,
  i: int,
  j: int,
  ni: dict,
  nj: dict,
  *,
  angle_th_deg: float,
  endpoint_tol: float,
  edge_kind: str,
) -> None:
  if edge_kind == "endpoint":
    rel = _endpoint_edge_relations(
      ni, nj, angle_th_deg=angle_th_deg, endpoint_tol=endpoint_tol,
    )
  else:
    rel = _geometry_edge_relations(
      ni, nj, angle_th_deg=angle_th_deg, endpoint_tol=endpoint_tol,
    )
  if rel is None:
    return
  graph.add_edge(i, j, edge_kind=edge_kind, **rel)


def _iter_endpoint_adjacent_pairs(
  info: list[dict],
  endpoint_link_gap: float,
) -> list[tuple[int, int]]:
  """Segment pairs whose endpoints are within ``endpoint_link_gap``."""
  if not info or endpoint_link_gap <= 0:
    return []

  cell = max(endpoint_link_gap, 1e-6)
  inv = 1.0 / cell
  endpoint_refs: list[tuple[int, np.ndarray]] = []
  buckets: dict[tuple[int, int], list[int]] = {}

  for seg_i, seg in enumerate(info):
    for ep in seg["endpoints"]:
      ref_idx = len(endpoint_refs)
      endpoint_refs.append((seg_i, ep))
      key = (int(np.floor(ep[0] * inv)), int(np.floor(ep[1] * inv)))
      buckets.setdefault(key, []).append(ref_idx)

  pairs: set[tuple[int, int]] = set()
  gap_sq = endpoint_link_gap * endpoint_link_gap
  for (cx, cy), members in buckets.items():
    pool: list[int] = []
    for dx in (-1, 0, 1):
      for dy in (-1, 0, 1):
        pool.extend(buckets.get((cx + dx, cy + dy), ()))
    pool = sorted(set(pool))
    for ai, a in enumerate(members):
      seg_i, ep_a = endpoint_refs[a]
      for b in pool[ai + 1:]:
        seg_j, ep_b = endpoint_refs[b]
        if seg_i == seg_j:
          continue
        if float(np.dot(ep_a - ep_b, ep_a - ep_b)) > gap_sq:
          continue
        pairs.add((seg_i, seg_j) if seg_i < seg_j else (seg_j, seg_i))
  return sorted(pairs)


def _init_segment_graph(info: list[dict]) -> nx.Graph:
  """Graph whose nodes are DXF segment records from ``extract_primitive_info``."""
  graph = nx.Graph()
  for i, d in enumerate(info):
    graph.add_node(i, geo_type=str(d["type"]).lower(), **d)
  return graph


def _cluster_endpoints(
  info: list[dict[str, Any]],
  gap: float,
) -> list[list[tuple[int, int]]]:
  """Union-find clusters of (segment_index, endpoint_index)."""
  refs: list[tuple[int, int, np.ndarray]] = []
  for seg_i, seg in enumerate(info):
    for ep_i, ep in enumerate(seg["endpoints"]):
      refs.append((seg_i, ep_i, ep))

  parent = list(range(len(refs)))

  def find(x: int) -> int:
    while parent[x] != x:
      parent[x] = parent[parent[x]]
      x = parent[x]
    return x

  def union(a: int, b: int) -> None:
    ra, rb = find(a), find(b)
    if ra != rb:
      parent[rb] = ra

  gap_sq = gap * gap
  cell = max(gap, 1e-6)
  inv = 1.0 / cell
  buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
  for idx, (_, _, ep) in enumerate(refs):
    key = (int(np.floor(ep[0] * inv)), int(np.floor(ep[1] * inv)))
    buckets[key].append(idx)

  for (cx, cy), members in buckets.items():
    pool: list[int] = []
    for dx in (-1, 0, 1):
      for dy in (-1, 0, 1):
        pool.extend(buckets.get((cx + dx, cy + dy), []))
    pool = sorted(set(pool))
    for ai, a in enumerate(members):
      _, _, ep_a = refs[a]
      for b in pool[ai + 1:]:
        _, _, ep_b = refs[b]
        if float(np.dot(ep_a - ep_b, ep_a - ep_b)) <= gap_sq:
          union(a, b)

  groups: dict[int, list[tuple[int, int]]] = defaultdict(list)
  for idx, (seg_i, ep_i, _) in enumerate(refs):
    groups[find(idx)].append((seg_i, ep_i))
  return list(groups.values())


def _ref_to_cluster_map(
  endpoint_clusters: list[list[tuple[int, int]]],
) -> dict[tuple[int, int], int]:
  mapping: dict[tuple[int, int], int] = {}
  for ci, cluster in enumerate(endpoint_clusters):
    for ref in cluster:
      mapping[ref] = ci
  return mapping


def _connecting_endpoint_cluster(
  u: int,
  v: int,
  nu: dict[str, Any],
  nv: dict[str, Any],
  max_gap: float,
  ref_cluster: dict[tuple[int, int], int],
) -> int | None:
  gap_sq = max_gap * max_gap
  best_ci: int | None = None
  best_d = gap_sq + 1.0
  for ep_i, ep in enumerate(nu["endpoints"]):
    for ep_j, ep2 in enumerate(nv["endpoints"]):
      d = float(np.dot(ep - ep2, ep - ep2))
      if d > gap_sq or d >= best_d:
        continue
      ci = ref_cluster.get((u, ep_i))
      cj = ref_cluster.get((v, ep_j))
      if ci is None or ci != cj:
        continue
      best_d = d
      best_ci = ci
  return best_ci


def _cluster_blocks_colinear_merge(
  cluster: list[tuple[int, int]],
  endpoint_graph: nx.Graph,
  min_degree: int,
) -> bool:
  """True when colinear chaining must not pass through this endpoint hub."""
  seg_ids = {seg_i for seg_i, _ in cluster}
  if len(seg_ids) >= min_degree:
    return True
  if any(_is_bridge_like(endpoint_graph.nodes[seg_i]) for seg_i in seg_ids):
    line_count = sum(
      1 for seg_i in seg_ids
      if _is_line_like(endpoint_graph.nodes[seg_i])
    )
    if line_count >= 2:
      return True
  return False


def attach_endpoint_clusters_to_graph(
  endpoint_graph: nx.Graph,
  info: list[dict[str, Any]],
  endpoint_clusters: list[list[tuple[int, int]]],
  *,
  max_gap: float,
) -> None:
  """Persist endpoint clusters on the graph and annotate connecting edges."""
  ref_cluster = _ref_to_cluster_map(endpoint_clusters)
  clusters_doc: dict[str, Any] = {}

  for ci, cluster in enumerate(endpoint_clusters):
    eid = f"E{ci + 1:04d}"
    pts: list[np.ndarray] = []
    members: list[dict[str, Any]] = []
    for seg_i, ep_i in cluster:
      handle = str(info[seg_i]["handle"])
      ep = np.asarray(info[seg_i]["endpoints"][ep_i], dtype=float)
      pts.append(ep)
      members.append({
        "handle": handle,
        "endpoint_index": int(ep_i),
      })
    center = np.mean(pts, axis=0) if pts else np.zeros(2)
    clusters_doc[eid] = {
      "center": [float(center[0]), float(center[1])],
      "members": members,
    }

  endpoint_graph.graph["endpoint_clusters"] = clusters_doc

  for u, v, data in endpoint_graph.edges(data=True):
    if data.get("edge_kind") != "endpoint":
      continue
    nu = endpoint_graph.nodes[u]
    nv = endpoint_graph.nodes[v]
    ci = _connecting_endpoint_cluster(u, v, nu, nv, max_gap, ref_cluster)
    if ci is not None:
      data["endpoint_cluster_id"] = f"E{ci + 1:04d}"


def build_endpoint_graph(
  info: list[dict],
  *,
  angle_th_deg: float = 5.0,
  endpoint_tol: float = 1e-3,
  endpoint_link_gap: float = 3.0,
) -> nx.Graph:
  """
  Endpoint-adjacency graph (``old/2-检测连续线段.py`` topology).

  Used only by ``detect_continuous_geometries`` to merge colinear wall segments.
  """
  graph = _init_segment_graph(info)
  graph.graph["kind"] = "endpoint_graph"
  if not info:
    return graph

  for i, j in _iter_endpoint_adjacent_pairs(info, endpoint_link_gap):
    _add_geometry_edge(
      graph,
      i,
      j,
      info[i],
      info[j],
      angle_th_deg=angle_th_deg,
      endpoint_tol=endpoint_tol,
      edge_kind="endpoint",
    )
  return graph

def _geometry_record_to_line_row(record: dict[str, Any], handle_key: str) -> dict[str, Any]:
  """Build a LINE geometry row from wall_line / stub / merged segment record."""
  attrs = record.get("attributes", {})
  start_raw, end_raw = attrs.get("start"), attrs.get("end")
  if not start_raw or not end_raw:
    raise ValueError(f"LINE record missing start/end: {record.get(handle_key)}")
  start = np.array(start_raw[:2], dtype=float)
  end = np.array(end_raw[:2], dtype=float)
  length = float(np.linalg.norm(end - start))
  if length < 1e-8:
    raise ValueError(f"degenerate LINE: {record.get(handle_key)}")
  direction = (end - start) / length
  row: dict[str, Any] = {
    "handle": str(record.get(handle_key, "unknown")),
    "type": "line",
    "start": start,
    "end": end,
    "mid": (start + end) / 2,
    "length": length,
    "direction": direction,
    "endpoints": [start, end],
  }
  if "layer" in record:
    row["layer"] = record["layer"]
  if record.get("source_handles"):
    row["source_handles"] = list(record["source_handles"])
  if record.get("arc_handles"):
    row["arc_handles"] = list(record["arc_handles"])
  return row


def wall_lines_to_info(wall_lines: list[dict[str, Any]]) -> list[dict]:
  """Convert wall_lines.json records to extract_primitive_info layout."""
  info: list[dict] = []
  for wall in wall_lines:
    try:
      row = _geometry_record_to_line_row(wall, "wall_id")
    except ValueError:
      continue
    info.append(row)
  return info

